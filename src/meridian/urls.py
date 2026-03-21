"""URL building and QR code generation for VLESS connections."""

from __future__ import annotations

import shlex
import subprocess

from meridian.credentials import ServerCredentials
from meridian.models import ProtocolURL
from meridian.protocols import PROTOCOLS

# Human-readable labels for each protocol key.
_PROTOCOL_LABELS: dict[str, str] = {
    "reality": "Primary",
    "xhttp": "XHTTP",
    "wss": "CDN Backup",
}


def build_protocol_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
    *,
    xhttp_port: int = 0,
) -> list[ProtocolURL]:
    """Build VLESS connection URLs for a client across all active protocols.

    Iterates over ``PROTOCOLS`` in registry order and produces a
    ``ProtocolURL`` for every protocol whose URL can be built given the
    supplied arguments.  Protocols that are not active (e.g. WSS without a
    domain, XHTTP without a port) are omitted from the returned list.

    Args:
        name: Client display name (used in URL fragment).
        reality_uuid: UUID for Reality and XHTTP connections.
        wss_uuid: UUID for WSS connection (empty if not domain mode).
        creds: Server credentials with protocol configs.
        xhttp_port: XHTTP inbound port (0 = no XHTTP).

    Returns:
        Ordered list of ``ProtocolURL`` objects, one per active protocol.
    """
    ip = creds.server.ip or ""
    sni = creds.server.sni or "www.microsoft.com"
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""
    domain = creds.server.domain or ""
    ws_path = creds.wss.ws_path or ""

    # Shared kwargs for Reality-based protocols.
    reality_kwargs = {
        "ip": ip,
        "sni": sni,
        "public_key": public_key,
        "short_id": short_id,
    }

    result: list[ProtocolURL] = []

    for proto in PROTOCOLS.values():
        key = proto.key
        label = _PROTOCOL_LABELS.get(key, key.upper())
        url = ""

        if key == "reality":
            url = proto.build_url(reality_uuid, name, **reality_kwargs)
        elif key == "xhttp":
            if xhttp_port > 0:
                url = proto.build_url(reality_uuid, name, port=xhttp_port, **reality_kwargs)
        elif key == "wss":
            if domain and wss_uuid:
                url = proto.build_url(wss_uuid, name, domain=domain, ws_path=ws_path)
        else:
            # Generic fallback for future protocols — skip if we can't build.
            continue

        if url:
            result.append(ProtocolURL(key=key, label=label, url=url))

    return result


def generate_qr_terminal(url: str) -> str:
    """Generate a QR code for terminal display using qrencode."""
    try:
        result = subprocess.run(
            ["qrencode", "-t", "ANSIUTF8", url],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def generate_qr_base64(url: str) -> str:
    """Generate a QR code as base64-encoded PNG for HTML embedding.

    Uses ``base64 | tr -d '\\n'`` for macOS compatibility (no -w0).
    """
    try:
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"printf '%s' {shlex.quote(url)} | qrencode -t PNG -o - -s 6 | base64 | tr -d '\\n'",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""
