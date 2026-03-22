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
    creds: ServerCredentials,
    relay_ip: str,
    relay_name: str = "",
) -> RelayURLSet:
    """Build Reality-only connection URLs that route through a relay node.

    Only Reality+TCP works reliably through a dumb L4 relay because the
    Reality handshake is end-to-end.  XHTTP and WSS require TLS cert
    matching that would break with a relay IP.

    Args:
        name: Client display name.
        reality_uuid: UUID for Reality connection.
        creds: Exit server credentials (for SNI, public key, short ID).
        relay_ip: Relay node IP address (substituted for exit IP).
        relay_name: Friendly relay name (used in URL fragment).

    Returns:
        A ``RelayURLSet`` with Reality-only URLs via this relay.
    """
    from meridian.protocols import get_protocol

    reality_proto = get_protocol("reality")
    if reality_proto is None:
        return RelayURLSet(relay_ip=relay_ip, relay_name=relay_name, urls=[])

    sni = creds.server.sni or DEFAULT_SNI
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""

    suffix = f"-via-{relay_name}" if relay_name else f"-via-{relay_ip}"
    url = reality_proto.build_url(
        reality_uuid,
        f"{name}{suffix}",
        ip=relay_ip,
        sni=sni,
        public_key=public_key,
        short_id=short_id,
    )

    urls = [ProtocolURL(key="reality", label="Primary (via relay)", url=url)]
    return RelayURLSet(relay_ip=relay_ip, relay_name=relay_name, urls=urls)


def build_all_relay_urls(
    name: str,
    reality_uuid: str,
    creds: ServerCredentials,
) -> list[RelayURLSet]:
    """Build relay URL sets for all relays attached to the exit server.

    Returns an empty list if no relays are configured.
    """
    return [
        build_relay_urls(name, reality_uuid, creds, relay.ip, relay.name)
        for relay in creds.relays
    ]


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
