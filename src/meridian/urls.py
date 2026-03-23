"""URL building and QR code generation for VLESS connections."""

from __future__ import annotations

import shlex
import subprocess

from meridian.config import DEFAULT_SNI
from meridian.credentials import ServerCredentials
from meridian.models import ProtocolURL, RelayURLSet
from meridian.protocols import PROTOCOLS

# Module-level flag to warn about missing qrencode only once per session.
_qrencode_warned = False


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
    domain, XHTTP without a path) are omitted from the returned list.

    Args:
        name: Client display name (used in URL fragment).
        reality_uuid: UUID for Reality and XHTTP connections.
        wss_uuid: UUID for WSS connection (empty if not domain mode).
        creds: Server credentials with protocol configs.
        xhttp_port: XHTTP inbound port (0 = no XHTTP). Kept for legacy
            callers; the XHTTP path is read from creds.xhttp.xhttp_path.

    Returns:
        Ordered list of ``ProtocolURL`` objects, one per active protocol.
    """
    ip = creds.server.ip or ""
    sni = creds.server.sni or DEFAULT_SNI
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""
    domain = creds.server.domain or ""
    ws_path = creds.wss.ws_path or ""
    xhttp_path = creds.xhttp.xhttp_path or ""

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
        label = proto.display_label
        url = ""

        if key == "reality":
            url = proto.build_url(reality_uuid, name, **reality_kwargs)
        elif key == "xhttp":
            if xhttp_path or xhttp_port > 0:
                url = proto.build_url(
                    reality_uuid,
                    name,
                    ip=ip,
                    xhttp_path=xhttp_path,
                    domain=domain,
                )
        elif key == "wss":
            if domain and wss_uuid:
                url = proto.build_url(wss_uuid, name, domain=domain, ws_path=ws_path)
        else:
            # Generic fallback for future protocols — skip if we can't build.
            continue

        if url:
            result.append(ProtocolURL(key=key, label=label, url=url))

    return result


def build_relay_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
    relay_ip: str,
    relay_name: str = "",
) -> RelayURLSet:
    """Build connection URLs that route through a relay node.

    A dumb L4 relay forwards TCP transparently, so TLS goes end-to-end
    to the exit server.  All protocols work if we set explicit ``sni=``
    parameters pointing to the exit's TLS certificate identity:

    - **Reality**: uses its own handshake — works as-is with relay IP.
    - **XHTTP**: add ``sni=<exit_ip_or_domain>`` so Caddy's cert matches.
    - **WSS**: add ``sni=<domain>`` + ``host=<domain>`` (domain mode only).

    Args:
        name: Client display name.
        reality_uuid: UUID for Reality and XHTTP connections.
        wss_uuid: UUID for WSS connection (empty if not domain mode).
        creds: Exit server credentials (SNI, keys, paths).
        relay_ip: Relay node IP address (substituted for exit IP).
        relay_name: Friendly relay name (used in URL fragment).

    Returns:
        A ``RelayURLSet`` with all active protocol URLs via this relay.
    """
    from meridian.protocols import get_protocol

    exit_ip = creds.server.ip or ""
    sni = creds.server.sni or DEFAULT_SNI
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""
    domain = creds.server.domain or ""
    xhttp_path = creds.xhttp.xhttp_path or ""
    ws_path = creds.wss.ws_path or ""

    suffix = f"-via-{relay_name}" if relay_name else f"-via-{relay_ip}"
    relay_label = relay_name or relay_ip
    urls: list[ProtocolURL] = []

    # Reality — end-to-end Reality handshake, relay is fully transparent
    reality_proto = get_protocol("reality")
    if reality_proto is not None:
        url = reality_proto.build_url(
            reality_uuid,
            f"{name}{suffix}",
            ip=relay_ip,
            sni=sni,
            public_key=public_key,
            short_id=short_id,
        )
        urls.append(ProtocolURL(key="reality", label=f"Primary (via {relay_label})", url=url))

    # XHTTP — TLS goes to exit, explicit sni= makes Caddy cert match
    if xhttp_path:
        # sni must match exit's TLS certificate (domain or IP)
        xhttp_sni = domain or exit_ip
        xhttp_url = (
            f"vless://{reality_uuid}@{relay_ip}:443"
            f"?encryption=none&security=tls&sni={xhttp_sni}"
            f"&type=xhttp&path=%2F{xhttp_path}"
            f"#{name}{suffix}-XHTTP"
        )
        urls.append(ProtocolURL(key="xhttp", label=f"XHTTP (via {relay_label})", url=xhttp_url))

    # WSS — domain mode only, TLS sni+host must match domain cert
    if domain and wss_uuid and ws_path:
        wss_url = (
            f"vless://{wss_uuid}@{relay_ip}:443"
            f"?encryption=none&security=tls&sni={domain}"
            f"&type=ws&host={domain}&path=%2F{ws_path}"
            f"#{name}{suffix}-WSS"
        )
        urls.append(ProtocolURL(key="wss", label=f"CDN Backup (via {relay_label})", url=wss_url))

    return RelayURLSet(relay_ip=relay_ip, relay_name=relay_name, urls=urls)


def build_all_relay_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
) -> list[RelayURLSet]:
    """Build relay URL sets for all relays attached to the exit server.

    Returns an empty list if no relays are configured.
    """
    return [build_relay_urls(name, reality_uuid, wss_uuid, creds, relay.ip, relay.name) for relay in creds.relays]


def generate_qr_terminal(url: str) -> str:
    """Generate a QR code for terminal display using qrencode."""
    global _qrencode_warned  # noqa: PLW0603
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
        if not _qrencode_warned:
            from meridian.console import warn

            warn(
                "qrencode not installed — QR codes will be missing. "
                "Install: apt install qrencode (Linux) or brew install qrencode (macOS)"
            )
            _qrencode_warned = True
    return ""


def generate_qr_base64(url: str) -> str:
    """Generate a QR code as base64-encoded PNG for HTML embedding.

    Uses ``base64 | tr -d '\\n'`` for macOS compatibility (no -w0).
    """
    global _qrencode_warned  # noqa: PLW0603
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
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    if not _qrencode_warned:
        from meridian.console import warn

        warn(
            "qrencode not installed — QR codes will be missing. "
            "Install: apt install qrencode (Linux) or brew install qrencode (macOS)"
        )
        _qrencode_warned = True
    return ""
