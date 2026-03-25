"""PWA file generation and deployment helpers.

Centralizes the creation and upload of per-client PWA files
(index.html, config.json, manifest.webmanifest, sub.txt) and
shared static assets (app.js, styles.css, sw.js, icon.svg).

Called from:
- DeployConnectionPage / DeployPWAAssets provisioner steps
- ``commands/client.py`` (_deploy_client_page)
- ``commands/relay.py`` (relay page regeneration)
"""

from __future__ import annotations

import base64
import shlex
from typing import TYPE_CHECKING

from meridian.render import (
    render_config_json,
    render_manifest,
    render_pwa_shell,
    render_subscription,
)

if TYPE_CHECKING:
    from meridian.models import ProtocolURL, RelayURLSet
    from meridian.ssh import ServerConnection

# Static PWA assets shipped with the package (relative to templates/pwa/).
_STATIC_FILES = ("app.js", "styles.css", "sw.js", "icon.svg")


def generate_client_files(
    protocol_urls: list[ProtocolURL],
    server_ip: str,
    domain: str = "",
    *,
    client_name: str = "",
    relay_entries: list[RelayURLSet] | None = None,
    server_name: str = "",
    server_icon: str = "",
    color: str = "",
) -> dict[str, str]:
    """Generate all per-client PWA files as a {filename: content} dict.

    Returns a dict with keys: ``index.html``, ``config.json``,
    ``manifest.webmanifest``, ``sub.txt``.
    """
    return {
        "index.html": render_pwa_shell(client_name=client_name, server_name=server_name),
        "config.json": render_config_json(
            protocol_urls,
            server_ip=server_ip,
            domain=domain,
            client_name=client_name,
            relay_entries=relay_entries,
            server_name=server_name,
            server_icon=server_icon,
            color=color,
        ),
        "manifest.webmanifest": render_manifest(client_name=client_name, server_name=server_name),
        "sub.txt": render_subscription(
            protocol_urls,
            relay_entries=relay_entries,
        ),
    }


def upload_client_files(
    conn: ServerConnection,
    reality_uuid: str,
    files: dict[str, str],
) -> bool:
    """Upload per-client PWA files to ``/var/www/private/{uuid}/``.

    Uses base64 transport to safely handle large or special-character
    content (same pattern as ``upload_pwa_assets``).

    Returns True on success, False if any upload fails.
    """
    q_uuid = shlex.quote(reality_uuid)
    result = conn.run(
        f"mkdir -p /var/www/private/{q_uuid} && chown caddy:caddy /var/www/private/{q_uuid}",
        timeout=10,
    )
    if result.returncode != 0:
        return False
    for filename, content in files.items():
        b64 = base64.b64encode(content.encode()).decode()
        q_b64 = shlex.quote(b64)
        q_name = shlex.quote(filename)
        result = conn.run(
            f"printf '%s' {q_b64} | base64 -d > /var/www/private/{q_uuid}/{q_name} && "
            f"chown caddy:caddy /var/www/private/{q_uuid}/{q_name}",
            timeout=15,
        )
        if result.returncode != 0:
            return False
    return True


def load_pwa_static_assets() -> dict[str, bytes]:
    """Load shared PWA static assets from package data.

    Returns a dict mapping filename to file content bytes.
    """
    from importlib.resources import files

    pwa_dir = files("meridian") / "templates" / "pwa"
    assets: dict[str, bytes] = {}
    for name in _STATIC_FILES:
        resource = pwa_dir / name
        assets[name] = resource.read_bytes()
    return assets


def upload_pwa_assets(conn: ServerConnection) -> bool:
    """Upload shared PWA static assets to ``/var/www/private/pwa/``.

    Deploys app.js, styles.css, sw.js, and icon.svg. These are
    identical for all clients and shared across connection pages.

    Returns True on success, False if any upload fails.
    """
    assets = load_pwa_static_assets()

    result = conn.run("mkdir -p /var/www/private/pwa && chown caddy:caddy /var/www/private/pwa", timeout=10)
    if result.returncode != 0:
        return False

    for filename, content in assets.items():
        # All our assets are text/SVG, safe to use printf
        b64 = base64.b64encode(content).decode()
        q_b64 = shlex.quote(b64)
        q_name = shlex.quote(filename)
        result = conn.run(
            f"printf '%s' {q_b64} | base64 -d > /var/www/private/pwa/{q_name} && "
            f"chown caddy:caddy /var/www/private/pwa/{q_name}",
            timeout=15,
        )
        if result.returncode != 0:
            return False
    return True
