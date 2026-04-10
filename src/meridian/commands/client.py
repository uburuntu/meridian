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
from meridian.render import save_connection_html
from meridian.servers import ServerRegistry
from meridian.ssh import SSH_OPTS
from meridian.urls import build_all_relay_urls, build_protocol_urls

if TYPE_CHECKING:
    from meridian.commands.resolve import ResolvedServer
    from meridian.models import ProtocolURL, RelayURLSet
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
        fail("No credentials found", hint="Deploy the server first: meridian deploy", hint_type="user")

    creds = ServerCredentials.load(proxy_file)
    if not creds.has_credentials:
        fail("No panel credentials found", hint="Deploy the server first: meridian deploy", hint_type="user")
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
            hint="Check credentials or run: meridian deploy",
            hint_type="system",
        )
    return panel


def _sync_credentials_to_server(resolved: ResolvedServer) -> bool:
    """Sync local credentials back to the server's /etc/meridian/."""
    if resolved.local_mode:
        return True  # Already on the server

    # SCP the credentials directory to the server
    try:
        result = subprocess.run(
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
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _refresh_credentials_or_fail(resolved: ResolvedServer, *, action: str) -> None:
    """Force-refresh credentials before mutating local state."""
    if fetch_credentials(resolved, force=True):
        return
    fail(
        f"Could not refresh credentials before {action}",
        hint="Check SSH/SCP and retry. Meridian will not mutate cached state without a fresh server read.",
        hint_type="system",
    )


def _save_credentials_with_sync(
    resolved: ResolvedServer,
    creds: ServerCredentials,
    *,
    recovery_hint: str,
) -> None:
    """Persist credentials locally and fail closed if server sync fails."""
    proxy_file = resolved.creds_dir / "proxy.yml"
    original_bytes = proxy_file.read_bytes() if proxy_file.exists() else None

    creds.save(proxy_file)
    if _sync_credentials_to_server(resolved):
        return

    if original_bytes is None:
        proxy_file.unlink(missing_ok=True)
    else:
        proxy_file.write_bytes(original_bytes)
        proxy_file.chmod(0o600)

    fail(
        "Could not sync updated credentials to server",
        hint=recovery_hint,
        hint_type="system",
    )


def _deploy_client_page(
    resolved: ResolvedServer,
    creds: ServerCredentials,
    protocol_urls: list[ProtocolURL],
    client_name: str,
    reality_uuid: str,
    relay_entries: list[RelayURLSet] | None = None,
) -> str:
    """Render and upload PWA connection page files for a client.

    Returns the hosted page URL, or empty string on failure.
    """
    from dataclasses import replace as dc_replace

    from meridian.pwa import generate_client_files, upload_client_files
    from meridian.urls import generate_qr_base64

    info_page_path = creds.panel.info_page_path or ""
    server_ip = creds.server.ip or resolved.ip
    domain = creds.server.domain or ""

    # Attach QR codes to protocol URLs
    urls_with_qr = [dc_replace(p, qr_b64=generate_qr_base64(p.url)) if p.url else p for p in protocol_urls]

    host = domain or server_ip
    page_url = f"https://{host}/{info_page_path}/{reality_uuid}/"

    client_files = generate_client_files(
        urls_with_qr,
        server_ip=server_ip,
        domain=domain,
        client_name=client_name,
        relay_entries=relay_entries,
        server_name=creds.branding.server_name,
        server_icon=creds.branding.icon,
        color=creds.branding.color,
        page_url=page_url,
    )

    conn = resolved.conn
    upload_error = upload_client_files(conn, reality_uuid, client_files)
    if upload_error:
        warn(f"Could not deploy server-hosted connection page: {upload_error}")
        return ""

    return page_url


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
    _refresh_credentials_or_fail(resolved, action=f"adding client '{name}'")

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
                hint="Deploy first: meridian deploy",
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

        # Add client to relay-specific inbounds (per-relay SNI)
        for relay in creds.relays:
            if not relay.sni:
                continue
            from meridian.commands.relay import _relay_inbound_remark, _relay_label

            remark = _relay_inbound_remark(relay)
            relay_ib = panel.find_inbound(remark)
            if relay_ib is None:
                continue
            relay_email = f"relay-{_relay_label(relay)}-{name}"
            relay_client = {
                "clients": [
                    {
                        "id": reality_uuid,
                        "flow": "xtls-rprx-vision",
                        "email": relay_email,
                        "limitIp": 2,
                        "totalGB": 0,
                        "expiryTime": 0,
                        "enable": True,
                        "tgId": "",
                        "subId": "",
                        "reset": 0,
                    }
                ],
            }
            try:
                panel.add_client(relay_ib.id, relay_client)
            except PanelError:
                warn(f"Could not add client to relay inbound {remark}")

        # Update credentials file
        creds.clients.append(
            ClientEntry(
                name=name,
                added=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                reality_uuid=reality_uuid,
                wss_uuid=wss_uuid,
            )
        )
        _save_credentials_with_sync(
            resolved,
            creds,
            recovery_hint=(
                f"The client may already exist on the panel. Once SSH/SCP works, run: "
                f"meridian client show {name} --server {resolved.ip}"
            ),
        )

        # Generate output files
        protocol_urls = build_protocol_urls(
            name=name,
            reality_uuid=reality_uuid,
            wss_uuid=wss_uuid,
            creds=creds,
            server_name=creds.branding.server_name,
        )

        # Build relay URL sets (if exit has relays)
        relay_url_sets = build_all_relay_urls(
            name,
            reality_uuid,
            wss_uuid,
            creds,
            server_name=creds.branding.server_name,
        )

        server_ip = creds.server.ip or resolved.ip
        file_prefix = f"{resolved.ip}-{name}"
        save_connection_html(
            protocol_urls,
            resolved.creds_dir / f"{file_prefix}-connection-info.html",
            server_ip,
            domain=domain,
            relay_entries=relay_url_sets,
        )

        # Deploy server-hosted connection page (if enabled)
        hosted_page_url = ""
        if creds.server.hosted_page and creds.panel.info_page_path:
            hosted_page_url = _deploy_client_page(
                resolved,
                creds,
                protocol_urls,
                name,
                reality_uuid,
                relay_entries=relay_url_sets or None,
            )

        # Print terminal output
        print_terminal_output(
            protocol_urls,
            resolved.creds_dir,
            server_ip,
            hosted_page_url=hosted_page_url,
            relay_entries=relay_url_sets or None,
        )

        err_console.print(f"  [dim]Test reachability: meridian test {resolved.ip}[/dim]")
        err_console.print("  [dim]View all clients:  meridian client list[/dim]\n")


# -- Client Show --


def run_show(
    name: str,
    user: str = "root",
    requested_server: str = "",
) -> None:
    """Display connection info for an existing client."""
    _validate_client_name(name)

    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)
    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    creds = _load_creds(resolved.creds_dir)

    # Find the client in credentials
    client_entry = next((c for c in creds.clients if c.name == name), None)
    if client_entry is None:
        # Client not in local creds — try to find in panel (handles credential sync gaps)
        panel = _make_panel(creds, resolved.conn)
        with panel:
            try:
                inbounds = panel.list_inbounds()
            except PanelError:
                fail(
                    f"Client '{name}' not found in credentials",
                    hint="Check client name with: meridian client list",
                    hint_type="user",
                )
            reality_proto = get_protocol("reality")
            if reality_proto is None:
                raise ValueError("Reality protocol not registered -- this is a bug")
            reality_inbound = reality_proto.find_inbound(inbounds)
            if reality_inbound is None:
                fail(
                    f"Client '{name}' not found",
                    hint="Check client name with: meridian client list",
                    hint_type="user",
                )

            # Find client by email
            reality_email = f"{reality_proto.email_prefix}{name}"
            reality_uuid = ""
            for client in reality_inbound.clients:
                if client.get("email") == reality_email:
                    reality_uuid = client.get("id", "")
                    break

            if not reality_uuid:
                fail(
                    f"Client '{name}' not found",
                    hint="Check client name with: meridian client list",
                    hint_type="user",
                )

            # Find WSS UUID if applicable
            wss_uuid = ""
            wss_proto = get_protocol("wss")
            if wss_proto:
                wss_inbound = wss_proto.find_inbound(inbounds)
                if wss_inbound:
                    wss_email = f"{wss_proto.email_prefix}{name}"
                    for client in wss_inbound.clients:
                        if client.get("email") == wss_email:
                            wss_uuid = client.get("id", "")
                            break

            # Sync back to credentials
            client_entry = ClientEntry(
                name=name,
                added=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                reality_uuid=reality_uuid,
                wss_uuid=wss_uuid,
            )
            creds.clients.append(client_entry)
            _save_credentials_with_sync(
                resolved,
                creds,
                recovery_hint=(
                    f"The client was found on the panel but Meridian could not publish refreshed credentials. "
                    f"Once SSH/SCP works, run: meridian client show {name} --server {resolved.ip}"
                ),
            )
            warn(f"Client '{name}' recovered from panel (credentials synced)")

    # Build protocol URLs
    protocol_urls = build_protocol_urls(
        name=name,
        reality_uuid=client_entry.reality_uuid,
        wss_uuid=client_entry.wss_uuid,
        creds=creds,
        server_name=creds.branding.server_name,
    )

    # Build relay URL sets (if exit has relays)
    relay_url_sets = build_all_relay_urls(
        name,
        client_entry.reality_uuid,
        client_entry.wss_uuid,
        creds,
        server_name=creds.branding.server_name,
    )

    server_ip = creds.server.ip or resolved.ip

    # Check for hosted page URL
    hosted_page_url = ""
    if creds.server.hosted_page and creds.panel.info_page_path and client_entry.reality_uuid:
        host = creds.server.domain or server_ip
        hosted_page_url = f"https://{host}/{creds.panel.info_page_path}/{client_entry.reality_uuid}/"

    # Print terminal output
    print_terminal_output(
        protocol_urls,
        resolved.creds_dir,
        server_ip,
        hosted_page_url=hosted_page_url,
        relay_entries=relay_url_sets or None,
        header_verb="connection info",
    )

    err_console.print(f"  [dim]Test reachability: meridian test {resolved.ip}[/dim]")
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
    _refresh_credentials_or_fail(resolved, action=f"removing client '{name}'")

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

        # Remove from relay-specific inbounds (per-relay SNI)
        for relay in creds.relays:
            if not relay.sni:
                continue
            from meridian.commands.relay import _relay_inbound_remark, _relay_label

            remark = _relay_inbound_remark(relay)
            relay_ib = panel.find_inbound(remark)
            if relay_ib is None:
                continue
            relay_email = f"relay-{_relay_label(relay)}-{name}"
            for client in relay_ib.clients:
                if client.get("email") == relay_email:
                    client_uuid = client.get("id", "")
                    if client_uuid:
                        try:
                            panel.remove_client(relay_ib.id, client_uuid)
                        except PanelError:
                            pass  # best-effort
                    break

        # Update credentials file
        creds.clients = [c for c in creds.clients if c.name != name]
        creds.save(resolved.creds_dir / "proxy.yml")
        if not _sync_credentials_to_server(resolved):
            warn("Could not sync credentials to server")

        # Delete local output files
        for pattern in [
            f"*-{name}-connection-info.html",
        ]:
            for f in resolved.creds_dir.glob(pattern):
                f.unlink(missing_ok=True)

        # Remove server-hosted connection page (if enabled)
        if creds.server.hosted_page:
            _remove_client_page(resolved, creds, name)

        err_console.print(f"\n  Client '{name}' has been removed from all active inbounds.\n")


# -- Display --


def _display_client_list_from_inbounds(inbounds: list[Inbound]) -> None:
    """Display client list from parsed Inbound objects."""
    from rich.box import ROUNDED
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

    table = Table(
        title="Proxy Clients",
        show_lines=False,
        pad_edge=False,
        box=ROUNDED,
        padding=(0, 2),
    )
    table.add_column("Name", style="bold cyan")
    table.add_column("Status", justify="center")
    table.add_column("Protocols", style="dim")

    for c in reality_clients:
        email = c.get("email", "")
        name = email.removeprefix(reality_proto.email_prefix) if email.startswith(reality_proto.email_prefix) else email
        status = "[green]● active[/green]" if c.get("enable", True) else "[dim]● disabled[/dim]"
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
