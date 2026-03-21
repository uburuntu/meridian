"""Client management -- add, list, remove proxy clients."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.commands.resolve import (
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import SERVERS_FILE
from meridian.console import err_console, fail, info, ok, warn
from meridian.credentials import ClientEntry, ServerCredentials
from meridian.display import print_terminal_output
from meridian.models import Inbound
from meridian.panel import PanelClient, PanelError
from meridian.protocols import PROTOCOLS, Protocol, get_protocol
from meridian.render import render_hosted_html, save_connection_html, save_connection_text
from meridian.servers import ServerRegistry
from meridian.ssh import SSH_OPTS
from meridian.urls import build_protocol_urls

if TYPE_CHECKING:
    from meridian.commands.resolve import ResolvedServer
    from meridian.ssh import ServerConnection

# -- Helpers --


def _validate_client_name(name: str) -> None:
    """Validate client name format. Exits on invalid."""
    if not name:
        fail("Client name is required", hint="Usage: meridian client add NAME", hint_type="user")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
        fail(
            f"Client name '{name}' is invalid",
            hint="Use letters, numbers, hyphens, and underscores.",
            hint_type="user",
        )


def _load_creds(creds_dir: Path) -> ServerCredentials:
    """Load and validate credentials from creds_dir."""
    proxy_file = creds_dir / "proxy.yml"
    if not proxy_file.exists():
        fail("No credentials found", hint="Deploy the server first: meridian setup", hint_type="user")

    creds = ServerCredentials.load(proxy_file)
    if not creds.has_credentials:
        fail("No panel credentials found", hint="Deploy the server first: meridian setup", hint_type="user")
    return creds


def _make_panel(creds: ServerCredentials, conn: ServerConnection) -> PanelClient:
    """Create and authenticate a PanelClient."""
    panel = PanelClient(
        conn=conn,
        panel_port=creds.panel.port,
        web_base_path=creds.panel.web_base_path or "",
    )
    try:
        panel.login(creds.panel.username or "", creds.panel.password or "")
    except PanelError as e:
        fail(
            f"Could not connect to server panel: {e}",
            hint="Check credentials or run: meridian setup",
            hint_type="system",
        )
    return panel


def _sync_credentials_to_server(resolved: ResolvedServer) -> None:
    """Sync local credentials back to the server's /etc/meridian/."""
    if resolved.local_mode:
        return  # Already on the server

    # SCP the credentials directory to the server
    try:
        subprocess.run(
            [
                "scp",
                *SSH_OPTS,
                "-r",
                f"{resolved.creds_dir}/",
                f"{resolved.user}@{resolved.ip}:/etc/meridian/",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        warn("Could not sync credentials to server")


def _deploy_client_page(
    resolved: ResolvedServer,
    creds: ServerCredentials,
    protocol_urls: list,
    client_name: str,
    reality_uuid: str,
) -> str:
    """Render and upload a server-hosted connection page for a client.

    Returns the hosted page URL, or empty string on failure.
    """
    import shlex

    from meridian.urls import generate_qr_base64

    info_page_path = creds.panel.info_page_path or ""
    server_ip = creds.server.ip or resolved.ip
    domain = creds.server.domain or ""

    # Generate QR codes locally
    reality_url = next((p.url for p in protocol_urls if p.key == "reality"), "")
    xhttp_url = next((p.url for p in protocol_urls if p.key == "xhttp"), "")
    wss_url = next((p.url for p in protocol_urls if p.key == "wss"), "")

    reality_qr = generate_qr_base64(reality_url) if reality_url else ""
    xhttp_qr = generate_qr_base64(xhttp_url) if xhttp_url else ""
    wss_qr = generate_qr_base64(wss_url) if wss_url else ""

    html = render_hosted_html(
        reality_url=reality_url,
        xhttp_url=xhttp_url,
        wss_url=wss_url,
        server_ip=server_ip,
        domain=domain,
        client_name=client_name,
        reality_qr_b64=reality_qr,
        xhttp_qr_b64=xhttp_qr,
        wss_qr_b64=wss_qr,
    )

    # Upload to server
    conn = resolved.conn
    q_uuid = shlex.quote(reality_uuid)
    conn.run(
        f"mkdir -p /var/www/private/{q_uuid} && chown caddy:caddy /var/www/private/{q_uuid}",
        timeout=10,
    )

    q_html = shlex.quote(html)
    result = conn.run(
        f"printf '%s' {q_html} > /var/www/private/{q_uuid}/index.html && "
        f"chown caddy:caddy /var/www/private/{q_uuid}/index.html",
        timeout=15,
    )

    if result.returncode != 0:
        warn("Could not deploy server-hosted connection page")
        return ""

    return f"https://{server_ip}/{info_page_path}/{reality_uuid}/"


def _remove_client_page(
    resolved: ResolvedServer,
    creds: ServerCredentials,
    client_name: str,
) -> None:
    """Remove a client's server-hosted connection page."""
    import shlex

    # Find the client's reality_uuid from credentials
    client_entry = next((c for c in creds.clients if c.name == client_name), None)
    if not client_entry or not client_entry.reality_uuid:
        return

    conn = resolved.conn
    q_uuid = shlex.quote(client_entry.reality_uuid)
    conn.run(f"rm -rf /var/www/private/{q_uuid}", timeout=10)


# -- Client Add --


def run_add(
    name: str,
    user: str = "root",
    requested_server: str = "",
) -> None:
    """Add a new client to the proxy server via direct panel API calls."""
    _validate_client_name(name)

    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)
    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    creds = _load_creds(resolved.creds_dir)
    info(f"Adding client '{name}'...")

    # Check for duplicates in credentials
    if any(c.name == name for c in creds.clients):
        fail(f"Client '{name}' already exists", hint="Use: meridian client list", hint_type="user")

    # Connect to panel
    panel = _make_panel(creds, resolved.conn)
    with panel:
        # List inbounds and find active ones
        try:
            inbounds = panel.list_inbounds()
        except PanelError as e:
            fail(f"Could not retrieve server configuration: {e}", hint_type="system")

        # Reality is the canonical protocol -- must exist
        reality_proto = get_protocol("reality")
        if reality_proto is None:
            raise ValueError("Reality protocol not registered -- this is a bug")
        reality_inbound = reality_proto.find_inbound(inbounds)

        if reality_inbound is None:
            fail(
                "Server is not set up yet",
                hint="Deploy first: meridian setup",
                hint_type="system",
            )

        # Check if client already exists in the panel (by email)
        reality_email = f"{reality_proto.email_prefix}{name}"
        for client in reality_inbound.clients:
            if client.get("email") == reality_email:
                fail(f"Client '{name}' already exists on the panel", hint="Use: meridian client list", hint_type="user")

        # Generate UUIDs -- one for Reality (shared with XHTTP), one for WSS
        try:
            reality_uuid = panel.generate_uuid()
        except PanelError as e:
            fail(f"Failed to generate UUID: {e}", hint_type="system")

        wss_uuid = ""
        domain = creds.server.domain or ""

        # Build active protocol list: (protocol, inbound, uuid)
        active: list[tuple[Protocol, Inbound, str]] = []
        uuids: dict[str, str] = {"reality": reality_uuid}

        for proto in PROTOCOLS.values():
            ib = proto.find_inbound(inbounds)
            if ib is None:
                continue
            if proto.requires_domain and not domain:
                continue

            # Determine UUID: shared or unique
            if proto.shares_uuid_with and proto.shares_uuid_with in uuids:
                uuid = uuids[proto.shares_uuid_with]
            elif proto.key in uuids:
                uuid = uuids[proto.key]
            else:
                try:
                    uuid = panel.generate_uuid()
                except PanelError as e:
                    fail(f"Failed to generate UUID for {proto.key}: {e}", hint_type="system")
                uuids[proto.key] = uuid

            if proto.key == "wss":
                wss_uuid = uuid

            active.append((proto, ib, uuid))

        # Add client to each active inbound
        for proto, ib, uuid in active:
            email = f"{proto.email_prefix}{name}"
            client_settings = proto.client_settings(uuid, email)
            try:
                panel.add_client(ib.id, client_settings)
            except PanelError as e:
                fail(f"Failed to add client to {proto.remark}: {e}", hint_type="system")

        ok(f"Client '{name}' added to panel")

        # Update credentials file
        creds.clients.append(
            ClientEntry(
                name=name,
                added=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                reality_uuid=reality_uuid,
                wss_uuid=wss_uuid,
            )
        )
        creds.save(resolved.creds_dir / "proxy.yml")

        # Find XHTTP port for URL building
        xhttp_proto = get_protocol("xhttp")
        xhttp_port = 0
        if xhttp_proto is not None:
            xhttp_ib = xhttp_proto.find_inbound(inbounds)
            if xhttp_ib is not None:
                xhttp_port = xhttp_ib.port

        # Generate output files
        protocol_urls = build_protocol_urls(
            name=name,
            reality_uuid=reality_uuid,
            wss_uuid=wss_uuid,
            creds=creds,
            xhttp_port=xhttp_port,
        )

        server_ip = creds.server.ip or resolved.ip
        file_prefix = f"{resolved.ip}-{name}"
        save_connection_text(
            protocol_urls,
            resolved.creds_dir / f"{file_prefix}-connection-info.txt",
            server_ip,
        )
        save_connection_html(
            protocol_urls,
            resolved.creds_dir / f"{file_prefix}-connection-info.html",
            server_ip,
            domain=domain,
        )

        # Sync credentials to server
        _sync_credentials_to_server(resolved)

        # Deploy server-hosted connection page (if enabled)
        hosted_page_url = ""
        if creds.server.hosted_page and creds.panel.info_page_path:
            hosted_page_url = _deploy_client_page(resolved, creds, protocol_urls, name, reality_uuid)

        # Print terminal output
        print_terminal_output(
            protocol_urls,
            resolved.creds_dir,
            server_ip,
            hosted_page_url=hosted_page_url,
        )

        err_console.print(f"  [dim]Test reachability: meridian ping {resolved.ip}[/dim]")
        err_console.print("  [dim]View all clients:  meridian client list[/dim]\n")


# -- Client List --


def run_list(
    user: str = "root",
    requested_server: str = "",
) -> None:
    """List all clients via direct panel API query."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    creds = _load_creds(resolved.creds_dir)
    panel = _make_panel(creds, resolved.conn)
    with panel:
        try:
            inbounds = panel.list_inbounds()
        except PanelError as e:
            fail(f"Could not retrieve server configuration: {e}", hint_type="system")

        _display_client_list_from_inbounds(inbounds)


# -- Client Remove --


def run_remove(
    name: str,
    user: str = "root",
    requested_server: str = "",
) -> None:
    """Remove a client from the proxy server via direct panel API calls."""
    _validate_client_name(name)

    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)
    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    creds = _load_creds(resolved.creds_dir)
    info(f"Removing client '{name}'...")

    panel = _make_panel(creds, resolved.conn)
    with panel:
        try:
            inbounds = panel.list_inbounds()
        except PanelError as e:
            fail(f"Could not retrieve server configuration: {e}", hint_type="system")

        # Verify client exists in Reality inbound (canonical)
        reality_proto = get_protocol("reality")
        if reality_proto is None:
            raise ValueError("Reality protocol not registered -- this is a bug")
        reality_inbound = reality_proto.find_inbound(inbounds)

        if reality_inbound is None:
            fail("No Reality inbound found on the server", hint_type="system")

        # Find client by email in Reality inbound
        client_email = f"{reality_proto.email_prefix}{name}"
        client_found = False
        for client in reality_inbound.clients:
            if client.get("email") == client_email:
                client_found = True
                break

        if not client_found:
            fail(f"Client '{name}' not found", hint="Check client name with: meridian client list", hint_type="user")

        # Remove from each active protocol's inbound
        for proto in PROTOCOLS.values():
            email = f"{proto.email_prefix}{name}"
            ib = proto.find_inbound(inbounds)
            if ib is None:
                continue
            # Find client UUID by email
            for client in ib.clients:
                if client.get("email") == email:
                    client_uuid = client.get("id", "")
                    if client_uuid:
                        try:
                            panel.remove_client(ib.id, client_uuid)
                        except PanelError as e:
                            warn(f"Failed to remove from {proto.remark}: {e}")

        ok(f"Client '{name}' removed from panel")

        # Update credentials file
        creds.clients = [c for c in creds.clients if c.name != name]
        creds.save(resolved.creds_dir / "proxy.yml")

        # Delete local output files
        for pattern in [
            f"*-{name}-connection-info.html",
            f"*-{name}-connection-info.txt",
        ]:
            for f in resolved.creds_dir.glob(pattern):
                f.unlink(missing_ok=True)

        # Remove server-hosted connection page (if enabled)
        if creds.server.hosted_page:
            _remove_client_page(resolved, creds, name)

        # Sync credentials to server
        _sync_credentials_to_server(resolved)

        err_console.print(f"\n  Client '{name}' has been removed from all active inbounds.\n")


# -- Display --


def _display_client_list_from_inbounds(inbounds: list[Inbound]) -> None:
    """Display client list from parsed Inbound objects."""
    from rich.table import Table

    # Build lookup: remark -> set of client emails
    clients_by_remark: dict[str, set[str]] = {}
    for ib in inbounds:
        emails = {c.get("email", "") for c in ib.clients}
        clients_by_remark[ib.remark] = emails

    # Reality is the canonical protocol
    reality_proto = get_protocol("reality")
    if reality_proto is None:
        raise ValueError("Reality protocol not registered -- this is a bug")
    reality_clients: list[dict] = []
    reality_ib = reality_proto.find_inbound(inbounds)
    if reality_ib is not None:
        reality_clients = reality_ib.clients

    # Build email sets for non-canonical protocols
    other_protocols = [p for p in PROTOCOLS.values() if p.key != "reality"]
    other_emails: dict[str, set[str]] = {p.key: clients_by_remark.get(p.remark, set()) for p in other_protocols}

    table = Table(title="Proxy Clients", show_lines=False, pad_edge=False, box=None, padding=(0, 2))
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Protocols")

    for c in reality_clients:
        email = c.get("email", "")
        name = email.removeprefix(reality_proto.email_prefix) if email.startswith(reality_proto.email_prefix) else email
        status = "[green]active[/green]" if c.get("enable", True) else "[dim]disabled[/dim]"
        protos = ["Reality"]
        for p in other_protocols:
            if f"{p.email_prefix}{name}" in other_emails[p.key]:
                protos.append(p.key.upper())
        table.add_row(name, status, " + ".join(protos))

    count = len(reality_clients)
    suffix = "s" if count != 1 else ""

    err_console.print()
    err_console.print(table)
    err_console.print()
    err_console.print(f"  [dim]Total: {count} client{suffix}[/dim]")
    err_console.print()
    err_console.print("  [dim]Add: meridian client add NAME  |  Remove: meridian client remove NAME[/dim]")
    err_console.print()
