"""Panel configuration provisioning steps.

Replaces roles/xray/tasks/configure_panel.yml and apply_panel_settings.yml.
Generates credentials, configures the 3x-ui panel via REST API, and persists
credentials locally BEFORE changing the panel password (lockout prevention).
"""

from __future__ import annotations

import re
import secrets
import shlex
import string
import time
from pathlib import Path

from meridian.config import DEFAULT_PANEL_PORT, DEFAULT_SNI
from meridian.credentials import ServerCredentials
from meridian.panel import PanelClient, PanelError
from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_string(length: int, alphabet: str) -> str:
    """Generate a cryptographically random string from the given alphabet."""
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_lower_digits(length: int) -> str:
    return _random_string(length, string.ascii_lowercase + string.digits)


def _random_alnum(length: int) -> str:
    return _random_string(length, string.ascii_letters + string.digits)


def _random_hex(length: int) -> str:
    return secrets.token_hex(length // 2)


# ---------------------------------------------------------------------------
# ConfigurePanel
# ---------------------------------------------------------------------------


class ConfigurePanel:
    """Generate credentials, save locally, configure 3x-ui panel via API.

    Replaces: configure_panel.yml + apply_panel_settings.yml

    Idempotency: skipped when panel_configured is already True in the
    credentials file (loaded into ctx before this step runs).

    SAFETY: Credentials are written to disk BEFORE the panel password is
    changed. If the playbook crashes mid-change, the user still has the
    new credentials saved locally.
    """

    name = "Configure panel"

    def __init__(
        self,
        creds_path: Path,
        server_ip: str,
        domain: str = "",
        sni: str = DEFAULT_SNI,
        email: str = "",
        first_client_name: str = "default",
        panel_port: int = DEFAULT_PANEL_PORT,
        xhttp_enabled: bool = True,
    ) -> None:
        self.creds_path = creds_path
        self.server_ip = server_ip
        self.domain = domain
        self.sni = sni
        self.email = email
        self.first_client_name = first_client_name
        self.panel_port = panel_port
        self.xhttp_enabled = xhttp_enabled

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check if already configured
        creds = ctx.get("credentials")
        if creds is not None and ctx.get("panel_configured"):
            # Update mutable fields even on re-runs (may have changed)
            changed = False
            if creds.server.hosted_page != ctx.hosted_page:
                creds.server.hosted_page = ctx.hosted_page
                changed = True

            from meridian import __version__

            if creds.server.deployed_with != __version__:
                creds.server.deployed_with = __version__
                changed = True

            if changed:
                creds.save(self.creds_path)
                ctx["credentials"] = creds
            return StepResult(
                name=self.name,
                status="skipped",
                detail="Panel already configured (credentials exist)",
            )

        # -- Generate random credentials --
        panel_username = _random_lower_digits(12)
        panel_password = _random_alnum(24)
        web_base_path = _random_lower_digits(24)
        info_page_path = _random_lower_digits(24)
        ws_path = _random_lower_digits(16)
        xhttp_path = _random_lower_digits(16)

        # -- Discover Xray binary path --
        xray_bin = _discover_xray_binary(conn)

        # -- Generate x25519 keypair --
        private_key, public_key = _generate_x25519_keypair(conn, xray_bin)

        # -- Generate UUIDs --
        reality_uuid = _generate_uuid(conn, xray_bin)
        wss_uuid = _generate_uuid(conn, xray_bin)

        # -- Generate short_id (8 hex chars) --
        short_id = _random_hex(8)

        # -- Build and save credentials BEFORE changing panel password --
        if creds is None:
            creds = ServerCredentials()

        # Track which CLI version deployed this server
        from meridian import __version__

        creds.server.deployed_with = __version__

        creds.panel.username = panel_username
        creds.panel.password = panel_password
        creds.panel.web_base_path = web_base_path
        creds.panel.info_page_path = info_page_path
        creds.panel.port = self.panel_port
        creds.server.ip = self.server_ip
        creds.server.domain = self.domain
        creds.server.sni = self.sni
        creds.server.hosted_page = ctx.hosted_page
        creds.reality.uuid = reality_uuid
        creds.reality.private_key = private_key
        creds.reality.public_key = public_key
        creds.reality.short_id = short_id
        creds.wss.uuid = wss_uuid
        creds.wss.ws_path = ws_path
        creds.xhttp.xhttp_path = xhttp_path

        # Track first client
        from meridian.credentials import ClientEntry

        if not creds.clients:
            from datetime import datetime, timezone

            creds.clients.append(
                ClientEntry(
                    name=self.first_client_name,
                    added=datetime.now(tz=timezone.utc).isoformat(),
                    reality_uuid=reality_uuid,
                    wss_uuid=wss_uuid,
                )
            )

        # Extra field for panel_configured flag
        creds._extra["panel_configured"] = True

        # SAVE FIRST (lockout prevention)
        creds.save(self.creds_path)

        # -- Apply settings via API --
        try:
            _apply_panel_settings(conn, self.panel_port, web_base_path, panel_username, panel_password)
        except PanelError as e:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Panel API error: {e}",
            )

        # Update context for subsequent steps
        ctx["credentials"] = creds
        ctx["panel_configured"] = True
        ctx["panel_username"] = panel_username
        ctx["panel_password"] = panel_password
        ctx["web_base_path"] = web_base_path
        ctx["info_page_path"] = info_page_path
        ctx["ws_path"] = ws_path
        ctx["xhttp_path"] = xhttp_path
        ctx["reality_uuid"] = reality_uuid
        ctx["reality_private_key"] = private_key
        ctx["reality_public_key"] = public_key
        ctx["reality_short_id"] = short_id
        ctx["wss_uuid"] = wss_uuid
        ctx["xray_bin"] = xray_bin

        return StepResult(
            name=self.name,
            status="changed",
            detail="Panel configured and credentials saved",
        )


# ---------------------------------------------------------------------------
# LoginToPanel
# ---------------------------------------------------------------------------


class LoginToPanel:
    """Login to the 3x-ui panel with saved credentials.

    Returns a PanelClient in ctx["panel"] for subsequent steps.
    """

    name = "Log in to panel"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        creds: ServerCredentials | None = ctx.get("credentials")
        if creds is None or not creds.has_credentials:
            return StepResult(
                name=self.name,
                status="failed",
                detail="No credentials available for panel login",
            )

        username = creds.panel.username
        password = creds.panel.password
        web_base_path = creds.panel.web_base_path or ""
        panel_port = creds.panel.port

        assert username is not None
        assert password is not None

        panel = PanelClient(conn, panel_port=panel_port, web_base_path=web_base_path)
        try:
            _wait_for_panel(conn, panel_port, web_base_path)
            panel.login(username, password)
        except PanelError as e:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Panel login failed: {e}",
            )

        ctx["panel"] = panel
        return StepResult(
            name=self.name,
            status="ok",
            detail=f"Logged in to panel at port {panel_port}",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _discover_xray_binary(conn: ServerConnection) -> str:
    """Find the Xray binary path inside the 3x-ui Docker container."""
    cmd = "docker exec 3x-ui sh -c 'ls /app/bin/xray-linux-* 2>/dev/null || which xray 2>/dev/null || echo NOT_FOUND'"
    result = conn.run(cmd, timeout=15)
    if result.returncode != 0:
        raise PanelError(f"Failed to discover Xray binary: {result.stderr.strip()}")

    binary = result.stdout.strip().splitlines()[0]
    if "NOT_FOUND" in binary:
        raise PanelError(
            "Xray binary not found in 3x-ui container. Try: docker exec 3x-ui find / -name 'xray*' -type f"
        )
    return binary


def _generate_x25519_keypair(conn: ServerConnection, xray_bin: str) -> tuple[str, str]:
    """Generate an x25519 keypair using the Xray binary.

    Returns (private_key, public_key).

    Handles both old format (Private key: / Public key:) and
    new format (PrivateKey: / Password:).
    """
    q_bin = shlex.quote(xray_bin)
    cmd = f"docker exec 3x-ui {q_bin} x25519"
    result = conn.run(cmd, timeout=15)
    if result.returncode != 0:
        raise PanelError(f"x25519 key generation failed: {result.stderr.strip()}")

    output = result.stdout
    private_match = re.search(r"(?:Private key|PrivateKey):\s*(.+)", output)
    public_match = re.search(r"(?:Public key|Password):\s*(.+)", output)

    if not private_match or not public_match:
        raise PanelError(f"Failed to parse x25519 output. Format may have changed.\nOutput: {output}")

    private_key = private_match.group(1).strip()
    public_key = public_match.group(1).strip()

    if len(private_key) < 20 or len(public_key) < 20:
        raise PanelError(
            f"x25519 keys are too short (private={len(private_key)}, "
            f"public={len(public_key)}). The Xray version may have changed the output format."
        )

    return private_key, public_key


def _generate_uuid(conn: ServerConnection, xray_bin: str) -> str:
    """Generate a UUID using the Xray binary."""
    q_bin = shlex.quote(xray_bin)
    cmd = f"docker exec 3x-ui {q_bin} uuid"
    result = conn.run(cmd, timeout=15)
    if result.returncode != 0:
        raise PanelError(f"UUID generation failed: {result.stderr.strip()}")

    uuid = result.stdout.strip()
    if not uuid:
        raise PanelError("Xray uuid command returned empty output")
    return uuid


def _apply_panel_settings(
    conn: ServerConnection,
    panel_port: int,
    web_base_path: str,
    new_username: str,
    new_password: str,
) -> None:
    """Login with default admin/admin, apply settings, change credentials, restart.

    Replaces: apply_panel_settings.yml
    """
    # Step 1: Wait for panel to be ready, then login with default credentials
    _wait_for_panel(conn, panel_port, "")
    panel = PanelClient(conn, panel_port=panel_port, web_base_path="")
    panel.login("admin", "admin")

    # Step 2: Update panel settings (webBasePath, security, etc.)
    settings_body = {
        "webListen": "127.0.0.1",
        "webDomain": "",
        "webPort": panel_port,
        "webCertFile": "",
        "webKeyFile": "",
        "webBasePath": f"/{web_base_path}/",
        "sessionMaxAge": 60,
        "expireDiff": 0,
        "trafficDiff": 0,
        "remarkModel": "-full",
        "tgBotEnable": False,
        "tgBotToken": "",
        "tgBotChatId": "",
        "tgRunTime": "@daily",
        "tgBotBackup": False,
        "tgBotLoginNotify": True,
        "tgCpu": 80,
        "subEnable": False,
        "subListen": "",
        "subPort": 2096,
        "subPath": "/sub/",
        "subDomain": "",
        "subCertFile": "",
        "subKeyFile": "",
        "subUpdates": 12,
        "subEncrypt": True,
        "subShowInfo": False,
        "subURI": "",
        "subJsonPath": "/json/",
        "subJsonURI": "",
        "subJsonFragment": "",
        "subJsonMux": "",
        "subJsonRules": "",
        "datepicker": "gregorian",
        "pageSize": 50,
        "loginSecurity": True,
    }
    data = panel.api_post_json("/panel/setting/update", settings_body)
    if not data.get("success"):
        raise PanelError(f"Failed to update panel settings: {data.get('msg', 'unknown')}")

    # Step 3: Change admin credentials
    user_body = {
        "oldUsername": "admin",
        "oldPassword": "admin",
        "newUsername": new_username,
        "newPassword": new_password,
    }
    data = panel.api_post_json("/panel/setting/updateUser", user_body)
    if not data.get("success"):
        raise PanelError(f"Failed to update panel credentials: {data.get('msg', 'unknown')}")

    # Step 4: Restart container to apply webBasePath
    result = conn.run("docker restart 3x-ui", timeout=60)
    if result.returncode != 0:
        raise PanelError(f"Failed to restart 3x-ui: {result.stderr.strip()}")

    # Step 5: Wait for panel to come back up
    _wait_for_panel(conn, panel_port, web_base_path)

    # Step 6: Verify login with new credentials
    new_panel = PanelClient(conn, panel_port=panel_port, web_base_path=web_base_path)
    new_panel.login(new_username, new_password)

    # Cleanup cookie files
    panel.cleanup()
    new_panel.cleanup()


def _wait_for_panel(
    conn: ServerConnection,
    panel_port: int,
    web_base_path: str,
    retries: int = 30,
    delay: float = 2.0,
) -> None:
    """Wait for the panel to become responsive after restart.

    Polls the panel URL until it responds (200 status) or retries are exhausted.
    After first run, the panel root '/' returns 404 (webBasePath is set) --
    so we check the webBasePath URL.
    """
    url = f"http://127.0.0.1:{panel_port}/{web_base_path}/"
    q_url = shlex.quote(url)

    for attempt in range(retries):
        result = conn.run(
            f"curl -s -o /dev/null -w '%{{http_code}}' {q_url}",
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip() == "200":
            return
        time.sleep(delay)

    raise PanelError(
        f"Panel did not become responsive after {retries * delay:.0f}s. Check: docker logs 3x-ui --tail 30"
    )
