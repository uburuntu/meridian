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
    decryption: str = "none",
) -> str:
    """Build client settings JSON string for 3x-ui API.

    For Reality, pass flow="xtls-rprx-vision".
    For XHTTP and WSS, pass flow="" (or omit -- defaults to "").
    When decryption != "none", fallbacks must be omitted (Xray constraint).
    """
    settings: dict = {
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
        "decryption": decryption,
    }
    # fallbacks conflicts with decryption — omit when PQ encryption is active
    if decryption == "none":
        settings["fallbacks"] = []
    return json.dumps(settings)


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
                    "spiderX": f"/{short_id}",
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
                    "spiderX": f"/{short_id}",
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


def _xhttp_reverse_proxy_stream_settings(xhttp_path: str) -> str:
    """Build streamSettings for XHTTP behind a TLS reverse proxy (security: none, like WSS)."""
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
# CreateInbound — unified inbound creation step
# ---------------------------------------------------------------------------

# Human-readable labels for spinner output
_PROTOCOL_LABELS = {"reality": "Reality", "xhttp": "XHTTP", "wss": "WSS"}


class CreateInbound:
    """Create a VLESS inbound via the 3x-ui API.

    A single parameterized step that handles all inbound protocols.
    Protocol-specific behavior (UUID source, stream settings) is resolved
    from the protocol_key and credentials.
    """

    def __init__(
        self,
        protocol_key: str,
        port: int,
        first_client_name: str = "default",
        client_limit_ip: int = 2,
        client_total_gb: int = 0,
        fingerprint: str = DEFAULT_FINGERPRINT,
        listen: str = "",
        delete_on_port_mismatch: bool = False,
        ctx_exports: dict[str, str] | None = None,
    ) -> None:
        if protocol_key not in INBOUND_TYPES:
            raise ValueError(f"Unknown protocol_key: {protocol_key!r} (expected one of {list(INBOUND_TYPES)})")
        self.protocol_key = protocol_key
        self.port = port
        self.first_client_name = first_client_name
        self.client_limit_ip = client_limit_ip
        self.client_total_gb = client_total_gb
        self.fingerprint = fingerprint
        self.listen = listen
        self.delete_on_port_mismatch = delete_on_port_mismatch
        self.ctx_exports = ctx_exports or {}

        label = _PROTOCOL_LABELS.get(protocol_key, protocol_key)
        self.name = f"Create {label} inbound"

    def _get_uuid(self, creds: Any) -> str:
        """Resolve the UUID for this protocol from credentials."""
        if self.protocol_key in ("reality", "xhttp"):
            return creds.reality.uuid
        return creds.wss.uuid

    def _build_stream_settings(self, creds: Any) -> str | None:
        """Build the streamSettings JSON string for this protocol.

        Returns None if a required field is missing (caller returns failed).
        """
        if self.protocol_key == "reality":
            return _reality_stream_settings(
                sni=creds.server.sni,
                private_key=creds.reality.private_key,
                public_key=creds.reality.public_key,
                short_id=creds.reality.short_id,
                fingerprint=self.fingerprint,
            )
        elif self.protocol_key == "xhttp":
            xhttp_path = creds.xhttp.xhttp_path
            if not xhttp_path:
                return None
            return _xhttp_reverse_proxy_stream_settings(xhttp_path=xhttp_path)
        elif self.protocol_key == "wss":
            return _wss_stream_settings(ws_path=creds.wss.ws_path)
        else:
            return None

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel = ctx.panel
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        inbound_type = INBOUND_TYPES[self.protocol_key]
        remark = inbound_type.remark
        creds = ctx.credentials
        if creds is None:
            return StepResult(
                name=self.name,
                status="failed",
                detail="No credentials available — ConfigurePanel may have failed",
            )

        # Check if inbound already exists
        existing = panel.find_inbound(remark)
        if existing is not None:
            if self.delete_on_port_mismatch and (existing.port != self.port or existing.listen != self.listen):
                _delete_inbound(panel, existing.id, remark)
            else:
                return StepResult(
                    name=self.name,
                    status="skipped",
                    detail=f"{remark} inbound already exists",
                )

        # Pre-check: ensure port is not already in use by another service
        if not self.listen:  # binding to all interfaces
            port_check = conn.run(f"ss -tlnp sport = :{self.port} 2>/dev/null", timeout=10)
            if port_check.returncode == 0 and f":{self.port}" in port_check.stdout:
                # Allow if it's already our service (Xray/3x-ui) — re-deploy scenario
                if not any(svc in port_check.stdout for svc in ["3x-ui", "xray"]):
                    return StepResult(
                        name=self.name,
                        status="failed",
                        detail=f"Port {self.port} already in use by another service",
                    )

        uuid = self._get_uuid(creds)
        stream_settings = self._build_stream_settings(creds)
        if stream_settings is None:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Missing config for {self.protocol_key} — ConfigurePanel may have failed",
            )

        # Resolve PQ decryption for Reality inbound
        decryption = "none"
        if self.protocol_key == "reality" and creds.reality.encryption_private_key:
            decryption = creds.reality.encryption_private_key

        email = f"{inbound_type.email_prefix}{self.first_client_name}"
        body: dict[str, Any] = {
            "remark": remark,
            "enable": True,
            "listen": self.listen,
            "port": self.port,
            "protocol": "vless",
            "expiryTime": 0,
            "total": 0,
            "settings": _client_settings(
                uuid=uuid,
                client_email=email,
                flow=inbound_type.flow,
                client_limit_ip=self.client_limit_ip,
                client_total_gb=self.client_total_gb,
                decryption=decryption,
            ),
            "streamSettings": stream_settings,
            "sniffing": SNIFFING_JSON,
        }

        data = panel.api_post_json("/panel/api/inbounds/add", body)
        if not data.get("success"):
            msg = data.get("msg", "unknown error")
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to create {remark}: {msg}. Fix: run 'meridian teardown' then retry deploy.",
            )

        # Export context values (e.g., xhttp_port for downstream steps)
        for key, attr in self.ctx_exports.items():
            ctx[key] = getattr(self, attr)

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"{remark} created on {self.listen or '0.0.0.0'}:{self.port}",
        )


# ---------------------------------------------------------------------------
# DisableXrayLogs
# ---------------------------------------------------------------------------


# Log section that disables access logs and minimizes error output.
# access="none" disables per-connection access logging (privacy).
# error="none" disables error log file (errors still visible in docker logs
# briefly via stderr, but are not persisted to disk).
# loglevel="warning" suppresses routine info messages.
_XRAY_LOG_CONFIG = {
    "access": "none",
    "dnsLog": False,
    "error": "none",
    "loglevel": "warning",
    "maskAddress": "",
}


class DisableXrayLogs:
    """Ensure Xray access and error logs are disabled.

    Fetches the Xray config template from 3x-ui, patches the log section,
    and saves it back. Idempotent — skips if already correct.
    """

    name = "Disable Xray logs"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel = ctx.panel
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        # Fetch current Xray config template
        try:
            data = panel.api_post_empty("/panel/xray/")
        except PanelError as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to fetch Xray config: {e}")

        if not data.get("success"):
            return StepResult(name=self.name, status="failed", detail="Failed to fetch Xray config template")

        # The obj is a JSON string containing {xraySetting, inboundTags, ...}
        obj = data.get("obj", "")
        try:
            wrapper = json.loads(obj) if isinstance(obj, str) else obj
            template_str = wrapper.get("xraySetting", "")
            if isinstance(template_str, str):
                template = json.loads(template_str)
            else:
                template = template_str
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to parse Xray template: {e}")

        # Check if log section already matches
        current_log = template.get("log", {})
        if current_log == _XRAY_LOG_CONFIG:
            return StepResult(name=self.name, status="ok", detail="Logs already disabled")

        # Patch log section and save
        template["log"] = _XRAY_LOG_CONFIG
        updated_json = json.dumps(template)

        try:
            from urllib.parse import quote as urlquote

            form_data = f"xraySetting={urlquote(updated_json, safe='')}"
            save_data = panel.api_post_form("/panel/xray/update", form_data)
        except PanelError as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to save Xray config: {e}")

        if not save_data.get("success"):
            return StepResult(name=self.name, status="failed", detail=f"Save failed: {save_data.get('msg', 'unknown')}")

        # Restart Xray to apply the new config
        try:
            panel.api_post_empty("/panel/api/server/restartXrayService")
        except PanelError:
            pass  # Non-fatal — Xray will pick up config on next restart

        return StepResult(name=self.name, status="changed", detail="Access and error logs disabled")


# ---------------------------------------------------------------------------
# ConfigureGeoBlocking
# ---------------------------------------------------------------------------

_BLOCKED_OUTBOUND = {
    "protocol": "blackhole",
    "tag": "blocked",
}

_GEO_BLOCK_RULES = [
    {
        "type": "field",
        "outboundTag": "blocked",
        "domain": ["geosite:category-ru"],
    },
    {
        "type": "field",
        "outboundTag": "blocked",
        "ip": ["geoip:ru"],
    },
]


class ConfigureGeoBlocking:
    """Block traffic to Russian domains and IPs at the Xray routing level."""

    name = "Configure geo-blocking"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel = ctx.panel
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        try:
            data = panel.api_post_empty("/panel/xray/")
        except PanelError as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to fetch Xray config: {e}")

        if not data.get("success"):
            return StepResult(name=self.name, status="failed", detail="Failed to fetch Xray config template")

        obj = data.get("obj", "")
        try:
            wrapper = json.loads(obj) if isinstance(obj, str) else obj
            template_str = wrapper.get("xraySetting", "")
            template = json.loads(template_str) if isinstance(template_str, str) else template_str
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to parse Xray template: {e}")

        outbounds = template.get("outbounds", [])
        has_blocked = any(o.get("tag") == "blocked" for o in outbounds)

        routing = template.get("routing", {})
        rules = routing.get("rules", [])
        has_geo_rules = any(
            r.get("outboundTag") == "blocked"
            and ("geoip:ru" in r.get("ip", []) or "geosite:category-ru" in r.get("domain", []))
            for r in rules
        )

        if has_blocked and has_geo_rules:
            return StepResult(name=self.name, status="ok", detail="Geo-blocking already configured")

        if not has_blocked:
            outbounds.append(dict(_BLOCKED_OUTBOUND))
            template["outbounds"] = outbounds

        if not has_geo_rules:
            if "routing" not in template:
                template["routing"] = {}
            template["routing"]["rules"] = [dict(r) for r in _GEO_BLOCK_RULES] + rules

        updated_json = json.dumps(template)
        try:
            from urllib.parse import quote as urlquote

            form_data = f"xraySetting={urlquote(updated_json, safe='')}"
            save_data = panel.api_post_form("/panel/xray/update", form_data)
        except PanelError as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to save Xray config: {e}")

        if not save_data.get("success"):
            return StepResult(name=self.name, status="failed", detail=f"Save failed: {save_data.get('msg', 'unknown')}")

        try:
            panel.api_post_empty("/panel/api/server/restartXrayService")
        except PanelError:
            pass  # Non-fatal — Xray will pick up config on next restart

        return StepResult(name=self.name, status="changed", detail="Blocked geosite:category-ru + geoip:ru")


class DisableGeoBlocking:
    """Remove Russian geo-blocking rules from Xray routing (user opted out)."""

    name = "Disable geo-blocking"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel = ctx.panel
        if panel is None:
            return StepResult(name=self.name, status="failed", detail="No panel client in context")

        try:
            data = panel.api_post_empty("/panel/xray/")
        except PanelError as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to fetch Xray config: {e}")

        if not data.get("success"):
            return StepResult(name=self.name, status="failed", detail="Failed to fetch Xray config template")

        obj = data.get("obj", "")
        try:
            wrapper = json.loads(obj) if isinstance(obj, str) else obj
            template_str = wrapper.get("xraySetting", "")
            template = json.loads(template_str) if isinstance(template_str, str) else template_str
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to parse Xray template: {e}")

        outbounds = template.get("outbounds", [])
        has_blocked = any(o.get("tag") == "blocked" for o in outbounds)

        routing = template.get("routing", {})
        rules = routing.get("rules", [])
        has_geo_rules = any(
            r.get("outboundTag") == "blocked"
            and ("geoip:ru" in r.get("ip", []) or "geosite:category-ru" in r.get("domain", []))
            for r in rules
        )

        if not has_blocked and not has_geo_rules:
            return StepResult(name=self.name, status="ok", detail="Geo-blocking already disabled")

        if has_geo_rules:
            template["routing"]["rules"] = [
                r
                for r in rules
                if not (
                    r.get("outboundTag") == "blocked"
                    and ("geoip:ru" in r.get("ip", []) or "geosite:category-ru" in r.get("domain", []))
                )
            ]

        if has_blocked:
            # Only remove the blocked outbound if no other rules reference it
            remaining_rules = template.get("routing", {}).get("rules", [])
            blocked_still_used = any(r.get("outboundTag") == "blocked" for r in remaining_rules)
            if not blocked_still_used:
                template["outbounds"] = [o for o in outbounds if o.get("tag") != "blocked"]

        updated_json = json.dumps(template)
        try:
            from urllib.parse import quote as urlquote

            form_data = f"xraySetting={urlquote(updated_json, safe='')}"
            save_data = panel.api_post_form("/panel/xray/update", form_data)
        except PanelError as e:
            return StepResult(name=self.name, status="failed", detail=f"Failed to save Xray config: {e}")

        if not save_data.get("success"):
            return StepResult(name=self.name, status="failed", detail=f"Save failed: {save_data.get('msg', 'unknown')}")

        try:
            panel.api_post_empty("/panel/api/server/restartXrayService")
        except PanelError:
            pass  # Non-fatal — Xray will pick up config on next restart

        return StepResult(name=self.name, status="changed", detail="Removed geosite:category-ru + geoip:ru blocking")


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
        result = conn.run("docker exec 3x-ui pgrep -f xray", timeout=15)
        if result.returncode == 0:
            return StepResult(
                name=self.name,
                status="ok",
                detail="Xray process is running",
            )

        # Xray is not running -- collect logs for diagnostics
        logs_result = conn.run("docker logs 3x-ui --tail 30", timeout=15)
        logs = logs_result.stdout.strip() if logs_result.returncode == 0 else "(no logs)"

        creds_obj = ctx.credentials
        ip_hint = ""
        if creds_obj and creds_obj.server.ip:
            ip_hint = f" {creds_obj.server.ip}"

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
