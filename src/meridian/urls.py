"""URL building and QR code generation for VLESS connections."""

from __future__ import annotations

import base64
import io

import segno

from meridian.config import DEFAULT_FINGERPRINT, DEFAULT_SNI
from meridian.credentials import ServerCredentials
from meridian.models import ProtocolURL, RelayURLSet
from meridian.protocols import PROTOCOLS


def build_protocol_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
    server_name: str = "",
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
            url = proto.build_url(reality_uuid, name, server_name=server_name, **reality_kwargs)
        elif key == "xhttp":
            if xhttp_path:
                url = proto.build_url(
                    reality_uuid,
                    name,
                    server_name=server_name,
                    ip=ip,
                    xhttp_path=xhttp_path,
                    domain=domain,
                )
        elif key == "wss":
            if domain and wss_uuid:
                url = proto.build_url(wss_uuid, name, server_name=server_name, domain=domain, ws_path=ws_path)
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
    relay_port: int = 443,
    server_name: str = "",
) -> RelayURLSet:
    """Build connection URLs that route through a relay node.

    A dumb L4 relay forwards TCP transparently, so TLS goes end-to-end
    to the exit server.  All protocols work if we set explicit ``sni=``
    parameters pointing to the exit's TLS certificate identity:

    - **Reality**: uses its own handshake — works as-is with relay IP.
    - **XHTTP**: add ``sni=<exit_ip_or_domain>`` so nginx's cert matches.
    - **WSS**: add ``sni=<domain>`` + ``host=<domain>`` (domain mode only).

    Args:
        name: Client display name.
        reality_uuid: UUID for Reality and XHTTP connections.
        wss_uuid: UUID for WSS connection (empty if not domain mode).
        creds: Exit server credentials (SNI, keys, paths).
        relay_ip: Relay node IP address (substituted for exit IP).
        relay_name: Friendly relay name (used in URL fragment).
        relay_port: Relay listen port (default 443).

    Returns:
        A ``RelayURLSet`` with all active protocol URLs via this relay.
    """
    exit_ip = creds.server.ip or ""
    sni = creds.server.sni or DEFAULT_SNI
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""
    domain = creds.server.domain or ""
    xhttp_path = creds.xhttp.xhttp_path or ""
    ws_path = creds.wss.ws_path or ""

    suffix = f"-via-{relay_name}" if relay_name else f"-via-{relay_ip}"
    relay_label = relay_name or relay_ip
    fragment_base = f"{name} @ {server_name}" if server_name else name
    urls: list[ProtocolURL] = []

    # Reality — end-to-end Reality handshake, relay is fully transparent
    url = (
        f"vless://{reality_uuid}@{relay_ip}:{relay_port}"
        f"?encryption=none&flow=xtls-rprx-vision"
        f"&security=reality&sni={sni}&fp={DEFAULT_FINGERPRINT}"
        f"&pbk={public_key}&sid={short_id}"
        f"&type=tcp&headerType=none"
        f"#{fragment_base}{suffix}"
    )
    urls.append(ProtocolURL(key="reality", label=f"Primary (via {relay_label})", url=url))

    # XHTTP — TLS goes to exit, explicit sni= makes nginx cert match
    if xhttp_path:
        xhttp_sni = domain or exit_ip
        xhttp_url = (
            f"vless://{reality_uuid}@{relay_ip}:{relay_port}"
            f"?encryption=none&security=tls&sni={xhttp_sni}&fp={DEFAULT_FINGERPRINT}"
            f"&type=xhttp&path=%2F{xhttp_path}"
            f"#{fragment_base}{suffix}-XHTTP"
        )
        urls.append(ProtocolURL(key="xhttp", label=f"XHTTP (via {relay_label})", url=xhttp_url))

    # WSS — domain mode only, TLS sni+host must match domain cert
    if domain and wss_uuid and ws_path:
        wss_url = (
            f"vless://{wss_uuid}@{relay_ip}:{relay_port}"
            f"?encryption=none&security=tls&sni={domain}"
            f"&type=ws&host={domain}&path=%2F{ws_path}"
            f"#{fragment_base}{suffix}-WSS"
        )
        urls.append(ProtocolURL(key="wss", label=f"WSS (via {relay_label})", url=wss_url))

    return RelayURLSet(relay_ip=relay_ip, relay_name=relay_name, urls=urls)


def build_all_relay_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
    server_name: str = "",
) -> list[RelayURLSet]:
    """Build relay URL sets for all relays attached to the exit server.

    Returns an empty list if no relays are configured.
    """
    return [
        build_relay_urls(
            name,
            reality_uuid,
            wss_uuid,
            creds,
            relay.ip,
            relay.name,
            relay.port,
            server_name=server_name,
        )
        for relay in creds.relays
    ]


def generate_qr_terminal(url: str) -> str:
    """Generate a QR code for terminal display."""
    try:
        qr = segno.make(url)
        buf = io.StringIO()
        qr.terminal(out=buf, compact=True)
        return buf.getvalue()
    except Exception:
        return ""


def generate_qr_base64(url: str) -> str:
    """Generate a QR code as base64-encoded PNG for HTML embedding."""
    try:
        qr = segno.make(url)
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=6)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""
