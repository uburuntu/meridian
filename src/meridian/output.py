"""Connection output generation — backwards-compatible public API.

New code should import from the focused sub-modules directly:
  - ``meridian.urls``    — URL building and QR generation
  - ``meridian.render``  — HTML/text file output
  - ``meridian.display`` — terminal output

This module is kept for backwards compatibility. It re-exports the new
API and provides thin wrappers around the deprecated ``ClientURLs``-based
interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meridian.credentials import ServerCredentials
from meridian.display import print_terminal_output as _new_print
from meridian.models import ProtocolURL
from meridian.protocols import get_protocol
from meridian.render import save_connection_html as _new_save_html
from meridian.render import save_connection_text as _new_save_text

# Re-export new API so callers can import from either location.
from meridian.urls import (  # noqa: F401
    build_protocol_urls,
    generate_qr_base64,
    generate_qr_terminal,
)

__all__ = [
    "ClientURLs",
    "build_protocol_urls",
    "build_vless_urls",
    "generate_qr_base64",
    "generate_qr_terminal",
    "print_terminal_output",
    "save_connection_html",
    "save_connection_text",
]


@dataclass(frozen=True)
class ClientURLs:
    """VLESS connection URLs for a client.

    .. deprecated::
        Use ``build_protocol_urls()`` and ``list[ProtocolURL]`` instead.
        This dataclass will be removed in a future major version.
    """

    name: str
    reality: str
    xhttp: str  # empty string if XHTTP is not enabled
    wss: str  # empty string if domain mode is not enabled


def _to_protocol_urls(urls: ClientURLs) -> list[ProtocolURL]:
    """Convert legacy ClientURLs to list[ProtocolURL]."""
    result = [ProtocolURL(key="reality", label="Primary", url=urls.reality)]
    if urls.xhttp:
        result.append(ProtocolURL(key="xhttp", label="XHTTP", url=urls.xhttp))
    if urls.wss:
        result.append(ProtocolURL(key="wss", label="CDN Backup", url=urls.wss))
    return result


def build_vless_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
    *,
    xhttp_port: int = 0,
) -> ClientURLs:
    """Build VLESS connection URLs for a client.

    .. deprecated::
        Use ``build_protocol_urls()`` which returns ``list[ProtocolURL]``.
    """
    from meridian.config import DEFAULT_SNI

    ip = creds.server.ip or ""
    sni = creds.server.sni or DEFAULT_SNI
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""
    domain = creds.server.domain or ""
    ws_path = creds.wss.ws_path or ""

    reality_kwargs = {
        "ip": ip,
        "sni": sni,
        "public_key": public_key,
        "short_id": short_id,
    }

    reality_proto = get_protocol("reality")
    if reality_proto is None:
        raise ValueError("Reality protocol not registered -- this is a bug")
    reality_url = reality_proto.build_url(reality_uuid, name, **reality_kwargs)

    xhttp_url = ""
    if xhttp_port > 0:
        xhttp_proto = get_protocol("xhttp")
        if xhttp_proto is None:
            raise ValueError("XHTTP protocol not registered -- this is a bug")
        xhttp_url = xhttp_proto.build_url(reality_uuid, name, port=xhttp_port, **reality_kwargs)

    wss_url = ""
    if domain and wss_uuid:
        wss_proto = get_protocol("wss")
        if wss_proto is None:
            raise ValueError("WSS protocol not registered -- this is a bug")
        wss_url = wss_proto.build_url(wss_uuid, name, domain=domain, ws_path=ws_path)

    return ClientURLs(name=name, reality=reality_url, xhttp=xhttp_url, wss=wss_url)


def save_connection_text(
    urls: ClientURLs,
    dest: Path,
    server_ip: str,
) -> None:
    """Save a plain-text connection summary file.

    .. deprecated:: Use ``render.save_connection_text()`` with ``list[ProtocolURL]``.
    """
    _new_save_text(_to_protocol_urls(urls), dest, server_ip, client_name=urls.name)


def save_connection_html(
    urls: ClientURLs,
    dest: Path,
    server_ip: str,
    domain: str = "",
) -> None:
    """Save a connection info HTML page with QR codes.

    .. deprecated:: Use ``render.save_connection_html()`` with ``list[ProtocolURL]``.
    """
    _new_save_html(_to_protocol_urls(urls), dest, server_ip, domain, client_name=urls.name)


def print_terminal_output(
    urls: ClientURLs,
    creds_dir: Path,
    server_ip: str,
) -> None:
    """Print connection info with QR codes to the terminal.

    .. deprecated:: Use ``display.print_terminal_output()`` with ``list[ProtocolURL]``.
    """
    _new_print(_to_protocol_urls(urls), creds_dir, server_ip, client_name=urls.name)
