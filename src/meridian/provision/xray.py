"""Xray inbound creation provisioning steps.

Replaces roles/xray/tasks/configure_reality.yml, configure_reality_xhttp.yml,
and configure_wss.yml. Creates VLESS inbounds via the 3x-ui REST API.

CRITICAL: The ``settings``, ``streamSettings``, and ``sniffing`` fields must
be JSON **strings** (not nested objects). This is a 3x-ui Go struct quirk --
the Go types use ``string`` for these fields.
"""

from __future__ import annotations

import json
from typing import Any

from meridian.config import DEFAULT_FINGERPRINT
from meridian.panel import PanelClient, PanelError
from meridian.protocols import INBOUND_TYPES
from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# ---------------------------------------------------------------------------
# Sniffing JSON (shared across all inbound types)
# ---------------------------------------------------------------------------

SNIFFING_JSON = json.dumps(
    {
        "enabled": True,
        "destOverride": ["http", "tls", "quic", "fakedns"],
        "metadataOnly": False,
        "routeOnly": False,
    }
)


# ---------------------------------------------------------------------------
# Inbound body builders
# ---------------------------------------------------------------------------


def _client_settings(
    uuid: str,
    client_email: str,
    flow: str = "",
    client_limit_ip: int = 2,
    client_total_gb: int = 0,
) -> str:
    """Build client settings JSON string for 3x-ui API.

    For Reality, pass flow="xtls-rprx-vision".
    For XHTTP and WSS, pass flow="" (or omit -- defaults to "").
    """
    return json.dumps(
        {
            "clients": [
                {
                    "id": uuid,
                    "flow": flow,
                    "email": client_email,
                    "limitIp": client_limit_ip,
                    "totalGB": client_total_gb,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0,
                }
            ],
            "decryption": "none",
            "fallbacks": [],
        }
    )


def _reality_stream_settings(
    sni: str,
    private_key: str,
    public_key: str,
    short_id: str,
    fingerprint: str = DEFAULT_FINGERPRINT,
) -> str:
    """Build the streamSettings JSON string for Reality+TCP."""
    dest = f"{sni}:443"
    return json.dumps(
        {
            "network": "tcp",
            "security": "reality",
            "externalProxy": [],
            "realitySettings": {
                "show": False,
                "xver": 0,
                "dest": dest,
                "serverNames": [sni],
                "privateKey": private_key,
                "minClient": "",
                "maxClient": "",
                "maxTimediff": 0,
                "shortIds": [short_id],
                "settings": {
                    "publicKey": public_key,
                    "fingerprint": fingerprint,
                    "serverName": "",
                    "spiderX": "/",
                },
            },
            "tcpSettings": {
                "acceptProxyProtocol": False,
                "header": {"type": "none"},
            },
        }
    )


def _xhttp_stream_settings(
    sni: str,
    private_key: str,
    public_key: str,
    short_id: str,
    fingerprint: str = DEFAULT_FINGERPRINT,
    xhttp_mode: str = "packet-up",
    xhttp_path: str = "/",
) -> str:
    """Build the streamSettings JSON string for Reality+XHTTP."""
    dest = f"{sni}:443"
    return json.dumps(
        {
            "network": "xhttp",
            "security": "reality",
            "externalProxy": [],
            "realitySettings": {
                "show": False,
                "xver": 0,
                "dest": dest,
                "serverNames": [sni],
                "privateKey": private_key,
                "minClient": "",
                "maxClient": "",
                "maxTimediff": 0,
                "shortIds": [short_id],
                "settings": {
                    "publicKey": public_key,
                    "fingerprint": fingerprint,
                    "serverName": "",
                    "spiderX": "/",
                },
            },
            "xhttpSettings": {
                "mode": xhttp_mode,
                "path": xhttp_path,
            },
        }
    )


def _wss_stream_settings(ws_path: str) -> str:
    """Build the streamSettings JSON string for WSS."""
    return json.dumps(
        {
            "network": "ws",
            "security": "none",
            "externalProxy": [],
            "wsSettings": {
                "acceptProxyProtocol": False,
                "path": f"/{ws_path}",
                "host": "",
                "headers": {},
            },
        }
    )


def _xhttp_caddy_stream_settings(xhttp_path: str) -> str:
    """Build streamSettings for XHTTP behind Caddy (security: none, like WSS)."""
    return json.dumps(
        {
            "network": "xhttp",
            "security": "none",
            "externalProxy": [],
            "xhttpSettings": {
                "mode": "auto",
                "path": f"/{xhttp_path}",
            },
        }
    )


# ---------------------------------------------------------------------------
# CreateRealityInbound
# ---------------------------------------------------------------------------


class CreateRealityInbound:
    """Create the VLESS+Reality+TCP inbound (primary protocol).

    Replaces: configure_reality.yml

    Handles mode switching: if an inbound exists on the wrong port (e.g.,
    switching from no-domain to domain mode), it is deleted and recreated.
    """

    name = "Create Reality inbound"

    def __init__(
        self,
        port: int,
        first_client_name: str = "default",
        client_limit_ip: int = 2,
        client_total_gb: int = 0,
        fingerprint: str = DEFAULT_FINGERPRINT,
    ) -> None:
        self.port = port
        self.first_client_name = first_client_name
        self.client_limit_ip = client_limit_ip
        self.client_total_gb = client_total_gb
        self.fingerprint = fingerprint

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel: PanelClient | None = ctx.get("panel")
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        remark = INBOUND_TYPES["reality"].remark
        creds = ctx["credentials"]

        # Check if inbound already exists
        existing = panel.find_inbound(remark)
        if existing is not None:
            # Check for port mismatch (mode switch)
            if existing.port != self.port:
                _delete_inbound(panel, existing.id, remark)
            else:
                return StepResult(
                    name=self.name,
                    status="skipped",
                    detail=f"Reality inbound already exists on port {existing.port}",
                )

        # Build the inbound creation body
        email = f"reality-{self.first_client_name}"
        body: dict[str, Any] = {
            "remark": remark,
            "enable": True,
            "port": self.port,
            "protocol": "vless",
            "expiryTime": 0,
            "total": 0,
            "settings": _client_settings(
                uuid=creds.reality.uuid,
                client_email=email,
                flow="xtls-rprx-vision",
                client_limit_ip=self.client_limit_ip,
                client_total_gb=self.client_total_gb,
            ),
            "streamSettings": _reality_stream_settings(
                sni=creds.server.sni,
                private_key=creds.reality.private_key,
                public_key=creds.reality.public_key,
                short_id=creds.reality.short_id,
                fingerprint=self.fingerprint,
            ),
            "sniffing": SNIFFING_JSON,
        }

        data = panel.api_post_json("/panel/api/inbounds/add", body)
        if not data.get("success"):
            msg = data.get("msg", "unknown error")
            return StepResult(
                name=self.name,
                status="failed",
                detail=(f"Failed to create Reality inbound: {msg}. Fix: run 'meridian teardown' then retry deploy."),
            )

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"Reality inbound created on port {self.port}",
        )


# ---------------------------------------------------------------------------
# CreateXHTTPInbound
# ---------------------------------------------------------------------------


class CreateXHTTPInbound:
    """Create the VLESS+XHTTP inbound behind Caddy (TLS terminated by Caddy).

    Replaces: configure_reality_xhttp.yml

    Uses the same UUID as Reality (shared identity).
    XHTTP listens on 127.0.0.1 (traffic arrives via Caddy reverse proxy),
    following the same pattern as WSS.
    """

    name = "Create XHTTP inbound"

    def __init__(
        self,
        port: int,
        first_client_name: str = "default",
        client_limit_ip: int = 2,
        client_total_gb: int = 0,
    ) -> None:
        self.port = port
        self.first_client_name = first_client_name
        self.client_limit_ip = client_limit_ip
        self.client_total_gb = client_total_gb

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel: PanelClient | None = ctx.get("panel")
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        remark = INBOUND_TYPES["xhttp"].remark
        creds = ctx["credentials"]

        # Check if inbound already exists
        existing = panel.find_inbound(remark)
        if existing is not None:
            return StepResult(
                name=self.name,
                status="skipped",
                detail="XHTTP inbound already exists",
            )

        # Get xhttp_path from credentials (generated by ConfigurePanel)
        xhttp_path = creds.xhttp.xhttp_path or ctx.get("xhttp_path", "")
        if not xhttp_path:
            return StepResult(
                name=self.name,
                status="failed",
                detail="No xhttp_path found — ConfigurePanel may have failed",
            )

        # XHTTP shares reality_uuid
        email = f"xhttp-{self.first_client_name}"
        body: dict[str, Any] = {
            "remark": remark,
            "enable": True,
            "listen": "127.0.0.1",
            "port": self.port,
            "protocol": "vless",
            "expiryTime": 0,
            "total": 0,
            "settings": _client_settings(
                uuid=creds.reality.uuid,
                client_email=email,
                client_limit_ip=self.client_limit_ip,
                client_total_gb=self.client_total_gb,
            ),
            "streamSettings": _xhttp_caddy_stream_settings(
                xhttp_path=xhttp_path,
            ),
            "sniffing": SNIFFING_JSON,
        }

        data = panel.api_post_json("/panel/api/inbounds/add", body)
        if not data.get("success"):
            msg = data.get("msg", "unknown error")
            return StepResult(
                name=self.name,
                status="failed",
                detail=(f"Failed to create XHTTP inbound: {msg}. Fix: run 'meridian teardown' then retry deploy."),
            )

        # Store the port in context for connection info
        ctx["xhttp_port"] = self.port

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"XHTTP inbound created on 127.0.0.1:{self.port}",
        )


# ---------------------------------------------------------------------------
# CreateWSSInbound
# ---------------------------------------------------------------------------


class CreateWSSInbound:
    """Create the VLESS+WSS inbound (CDN fallback via Cloudflare).

    Replaces: configure_wss.yml

    Only created when domain mode is enabled. Listens on 127.0.0.1
    (traffic arrives via Caddy reverse proxy).
    """

    name = "Create WSS inbound"

    def __init__(
        self,
        port: int,
        first_client_name: str = "default",
        client_limit_ip: int = 2,
        client_total_gb: int = 0,
    ) -> None:
        self.port = port
        self.first_client_name = first_client_name
        self.client_limit_ip = client_limit_ip
        self.client_total_gb = client_total_gb

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel: PanelClient | None = ctx.get("panel")
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        remark = INBOUND_TYPES["wss"].remark
        creds = ctx["credentials"]

        # Check if inbound already exists
        existing = panel.find_inbound(remark)
        if existing is not None:
            return StepResult(
                name=self.name,
                status="skipped",
                detail="WSS inbound already exists",
            )

        email = f"wss-{self.first_client_name}"
        body: dict[str, Any] = {
            "remark": remark,
            "enable": True,
            "listen": "127.0.0.1",
            "port": self.port,
            "protocol": "vless",
            "expiryTime": 0,
            "total": 0,
            "settings": _client_settings(
                uuid=creds.wss.uuid,
                client_email=email,
                client_limit_ip=self.client_limit_ip,
                client_total_gb=self.client_total_gb,
            ),
            "streamSettings": _wss_stream_settings(
                ws_path=creds.wss.ws_path,
            ),
            "sniffing": SNIFFING_JSON,
        }

        data = panel.api_post_json("/panel/api/inbounds/add", body)
        if not data.get("success"):
            msg = data.get("msg", "unknown error")
            return StepResult(
                name=self.name,
                status="failed",
                detail=(f"Failed to create WSS inbound: {msg}. Fix: run 'meridian teardown' then retry deploy."),
            )

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"WSS inbound created on 127.0.0.1:{self.port}",
        )


# ---------------------------------------------------------------------------
# VerifyXray
# ---------------------------------------------------------------------------


class VerifyXray:
    """Verify that Xray core is running inside the 3x-ui container.

    If Xray crashed (e.g., due to a corrupted inbound config), the panel
    stays up but no traffic flows. This catches the failure early.
    """

    name = "Verify Xray configuration"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        result = conn.run("docker exec 3x-ui pgrep -f xray", timeout=10)
        if result.returncode == 0:
            return StepResult(
                name=self.name,
                status="ok",
                detail="Xray process is running",
            )

        # Xray is not running -- collect logs for diagnostics
        logs_result = conn.run("docker logs 3x-ui --tail 30", timeout=10)
        logs = logs_result.stdout.strip() if logs_result.returncode == 0 else "(no logs)"

        server_ip = ctx.get("credentials", None)
        ip_hint = ""
        if server_ip and hasattr(server_ip, "server") and server_ip.server.ip:
            ip_hint = f" {server_ip.server.ip}"

        return StepResult(
            name=self.name,
            status="failed",
            detail=(
                f"Xray core is not running inside the 3x-ui container.\n"
                f"This usually means the inbound configuration is invalid or the database is corrupted.\n"
                f"\nContainer logs (last 30 lines):\n{logs}\n"
                f"\nFix: run 'meridian teardown{ip_hint}' then retry deploy."
            ),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _delete_inbound(panel: PanelClient, inbound_id: int, remark: str) -> None:
    """Delete an inbound by ID (used for mode-switch port correction)."""
    data = panel.api_post_empty(f"/panel/api/inbounds/del/{inbound_id}")
    if not data.get("success"):
        raise PanelError(f"Failed to delete old {remark} inbound (id={inbound_id}): {data.get('msg', 'unknown error')}")
