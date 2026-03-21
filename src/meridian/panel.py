"""3x-ui panel REST API client -- runs commands via SSH.

All API calls execute curl on the remote server via ServerConnection.run().
Results are parsed as JSON in Python.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field

from meridian.ssh import ServerConnection


class PanelError(Exception):
    """Raised when a panel API call fails."""


@dataclass
class Inbound:
    """An inbound from the 3x-ui panel."""

    id: int
    remark: str
    protocol: str
    port: int
    clients: list[dict] = field(default_factory=list)
    stream_settings: dict = field(default_factory=dict)


class PanelClient:
    """Wraps 3x-ui REST API via SSH (curl on the server).

    Usage:
        panel = PanelClient(conn, panel_port=2053, web_base_path="abc123")
        panel.login(username, password)
        inbounds = panel.list_inbounds()
        panel.add_client(inbound_id, {...})
        panel.remove_client(inbound_id, client_uuid)
        panel.cleanup()
    """

    def __init__(self, conn: ServerConnection, panel_port: int, web_base_path: str) -> None:
        self.conn = conn
        self.base_url = f"http://127.0.0.1:{panel_port}/{web_base_path}"
        self._cookie_path = "$HOME/.meridian/.cookie"

    def login(self, username: str, password: str) -> None:
        """Login and store session cookie.

        IMPORTANT: Login uses form-urlencoded (not JSON) -- 3x-ui requirement.
        Values are URL-encoded to handle special characters (&, =, etc.).
        """
        from urllib.parse import quote as urlquote

        encoded_user = urlquote(username, safe="")
        encoded_pass = urlquote(password, safe="")
        form_data = f"username={encoded_user}&password={encoded_pass}"
        cmd = (
            f"mkdir -p $HOME/.meridian && chmod 700 $HOME/.meridian && "
            f"curl -s -c {self._cookie_path}"
            f" -d {shlex.quote(form_data)}"
            f" {shlex.quote(self.base_url + '/login')}"
        )
        result = self.conn.run(cmd, timeout=15)
        # Secure cookie file permissions (don't leave world-readable)
        self.conn.run(f"chmod 600 {self._cookie_path} 2>/dev/null", timeout=5)
        if result.returncode != 0:
            raise PanelError(f"Login request failed: {result.stderr.strip()}")

        raw = result.stdout.strip()
        if not raw:
            raise PanelError("Empty response from login endpoint")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PanelError(f"Invalid JSON from login: {e}") from e

        if not data.get("success"):
            raise PanelError(f"Login failed: {data.get('msg', 'unknown error')}")

    def _api_get(self, path: str) -> dict:
        """Make an authenticated GET request."""
        url = shlex.quote(self.base_url + path)
        cmd = f"curl -s -b {self._cookie_path} {url}"
        result = self.conn.run(cmd, timeout=15)
        if result.returncode != 0:
            raise PanelError(f"API GET {path} failed: {result.stderr.strip()}")
        return self._parse_response(result.stdout, path)

    def _api_post_json(self, path: str, body: dict) -> dict:
        """Make an authenticated POST request with JSON body.

        IMPORTANT: Inbound/client operations MUST use JSON (not form-urlencoded).
        Ansible's uri module silently corrupts inline JSON values in form-urlencoded.
        """
        url = shlex.quote(self.base_url + path)
        json_body = shlex.quote(json.dumps(body))
        cmd = f"curl -s -b {self._cookie_path} -H 'Content-Type: application/json' -d {json_body} {url}"
        result = self.conn.run(cmd, timeout=15)
        if result.returncode != 0:
            raise PanelError(f"API POST {path} failed: {result.stderr.strip()}")
        return self._parse_response(result.stdout, path)

    def _api_post_empty(self, path: str) -> dict:
        """Make an authenticated POST request with no body."""
        url = shlex.quote(self.base_url + path)
        cmd = f"curl -s -b {self._cookie_path} -X POST {url}"
        result = self.conn.run(cmd, timeout=15)
        if result.returncode != 0:
            raise PanelError(f"API POST {path} failed: {result.stderr.strip()}")
        return self._parse_response(result.stdout, path)

    @staticmethod
    def _parse_response(raw: str, context: str) -> dict:
        """Parse JSON response and verify success."""
        raw = raw.strip()
        if not raw:
            raise PanelError(f"Empty response from {context}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PanelError(f"Invalid JSON from {context}: {e}") from e
        return data

    def list_inbounds(self) -> list[Inbound]:
        """List all inbounds from the panel API."""
        data = self._api_get("/panel/api/inbounds/list")
        if not data.get("success"):
            raise PanelError(f"List inbounds failed: {data.get('msg', 'unknown error')}")

        result: list[Inbound] = []
        for obj in data.get("obj", []):
            settings = json.loads(obj.get("settings", "{}"))
            stream = json.loads(obj.get("streamSettings", "{}"))
            result.append(
                Inbound(
                    id=obj["id"],
                    remark=obj.get("remark", ""),
                    protocol=obj.get("protocol", ""),
                    port=obj.get("port", 0),
                    clients=settings.get("clients", []),
                    stream_settings=stream,
                )
            )
        return result

    def find_inbound(self, remark: str) -> Inbound | None:
        """Find an inbound by its remark string."""
        for ib in self.list_inbounds():
            if ib.remark == remark:
                return ib
        return None

    def add_client(self, inbound_id: int, client_settings: dict) -> None:
        """Add a client to an inbound.

        client_settings should contain a 'clients' array, e.g.:
            {"clients": [{"id": "uuid", "flow": "...", "email": "...", ...}]}

        IMPORTANT: The 'settings' field in the API body is a JSON STRING,
        not a nested object. This is a 3x-ui Go struct quirk.
        """
        body = {
            "id": inbound_id,
            "settings": json.dumps(client_settings),
        }
        data = self._api_post_json("/panel/api/inbounds/addClient", body)
        if not data.get("success"):
            raise PanelError(f"Add client failed: {data.get('msg', 'unknown error')}")

    def remove_client(self, inbound_id: int, client_uuid: str) -> None:
        """Remove a client from an inbound by UUID.

        IMPORTANT: Use the UUID-based endpoint, NOT email-based deletion.
        Email-based deletion silently succeeds but doesn't actually delete.
        """
        q_uuid = shlex.quote(client_uuid)
        path = f"/panel/api/inbounds/{inbound_id}/delClient/{q_uuid}"
        data = self._api_post_empty(path)
        if not data.get("success"):
            raise PanelError(f"Remove client failed: {data.get('msg', 'unknown error')}")

    def generate_uuid(self) -> str:
        """Generate a UUID using the Xray binary inside the 3x-ui container."""
        cmd = "docker exec 3x-ui sh -c 'ls /app/bin/xray-linux-* 2>/dev/null | head -1'"
        result = self.conn.run(cmd, timeout=10)
        if result.returncode != 0 or not result.stdout.strip():
            raise PanelError("Failed to discover Xray binary in 3x-ui container")

        xray_bin = result.stdout.strip()
        q_bin = shlex.quote(xray_bin)
        cmd = f"docker exec 3x-ui {q_bin} uuid"
        result = self.conn.run(cmd, timeout=10)
        if result.returncode != 0:
            raise PanelError(f"UUID generation failed: {result.stderr.strip()}")

        uuid = result.stdout.strip()
        if not uuid:
            raise PanelError("Xray uuid command returned empty output")
        return uuid

    def cleanup(self) -> None:
        """Remove the cookie file."""
        self.conn.run(f"rm -f {self._cookie_path}", timeout=5)

    def __enter__(self) -> PanelClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()
