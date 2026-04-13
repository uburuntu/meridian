"""Client management -- add, show, list, remove proxy clients.

All client state lives in Remnawave's database. No local proxy.yml,
no credential sync, no rollback. One API call per operation.
"""

from __future__ import annotations

import re

import typer

from meridian.cluster import ClusterConfig
from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.console import confirm, err_console, fail, info, is_json_mode, ok
from meridian.remnawave import MeridianPanel, RemnawaveError, User

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


def _format_status(status: str) -> str:
    """Format user status with Rich markup."""
    status_upper = status.upper()
    if status_upper == "ACTIVE":
        return "[green]● active[/green]"
    if status_upper == "DISABLED":
        return "[dim]● disabled[/dim]"
    if status_upper == "LIMITED":
        return "[yellow]● limited[/yellow]"
    if status_upper == "EXPIRED":
        return "[red]● expired[/red]"
    return f"[dim]● {status.lower()}[/dim]"


def _build_page_url(cluster: ClusterConfig, vless_uuid: str) -> str:
    """Build the connection page URL for a client, or empty string if unavailable."""
    info_page_path = cluster.panel.sub_path or ""
    if not info_page_path or not vless_uuid:
        return ""
    node = cluster.panel_node
    if not node:
        return ""
    host = node.domain or node.ip
    return f"https://{host}/{info_page_path}/{vless_uuid}/"


def _print_subscription(panel: MeridianPanel, user: User, *, page_url: str = "") -> None:
    """Print connection page URL and/or subscription URL with QR code."""
    from meridian.urls import generate_qr_terminal

    sub_url = panel.get_subscription_url(user.short_uuid)

    if page_url:
        err_console.print()
        err_console.print("  [bold]Share this link[/bold]")
        err_console.print(f"  {page_url}")
        err_console.print("  [dim](They open it, scan the QR code, and connect)[/dim]")
        qr = generate_qr_terminal(page_url)
        if qr:
            err_console.print()
            err_console.print(qr)
        err_console.print()
        err_console.print("  [bold]Subscription URL[/bold] [dim](for Xray/V2Ray apps)[/dim]")
        err_console.print(f"  {sub_url}")
    else:
        err_console.print()
        err_console.print("  [bold]Subscription URL[/bold]")
        err_console.print(f"  {sub_url}")
        qr = generate_qr_terminal(sub_url)
        if qr:
            err_console.print()
            err_console.print(qr)


# -- Client Add --


def run_add(
    name: str,
    user: str = "",
    requested_server: str = "",
) -> None:
    """Add a new client to the proxy cluster."""
    _validate_client_name(name)
    cluster = load_cluster()
    panel = make_panel(cluster)

    info(f"Adding client '{name}'...")

    with panel:
        # Check if user already exists
        existing = panel.get_user(name)
        if existing is not None:
            fail(
                f"Client '{name}' already exists",
                hint="Use: meridian client show " + name,
                hint_type="user",
            )

        # Create the user -- one API call
        try:
            squad_uuids = [cluster.squad_uuid] if cluster.squad_uuid else None
            new_user = panel.create_user(name, squad_uuids=squad_uuids)
        except RemnawaveError as e:
            fail(
                f"Could not create client: {e}",
                hint=e.hint or "Check panel connectivity",
                hint_type=e.hint_type,
            )

        ok(f"Client '{name}' added")

        # Build page URL (deterministic from cluster data)
        page_url = _build_page_url(cluster, new_user.vless_uuid)
        _print_subscription(panel, new_user, page_url=page_url)

        # Deploy connection page files on the panel host
        if page_url and cluster.panel.server_ip:
            panel_node = cluster.panel_node
            if panel_node:
                try:
                    from meridian.commands.setup import _deploy_client_page
                    from meridian.ssh import ServerConnection

                    sub_url = panel.get_subscription_url(new_user.short_uuid) if new_user.short_uuid else ""
                    with ServerConnection(
                        cluster.panel.server_ip,
                        user=cluster.panel.ssh_user or "root",
                        port=getattr(cluster.panel, "ssh_port", 22) or 22,
                    ) as conn:
                        _deploy_client_page(conn, cluster, panel_node, new_user.vless_uuid, name, sub_url)
                except Exception:
                    pass  # Non-fatal — subscription URL still works

    err_console.print()
    err_console.print("  [dim]Show client:       meridian client show " + name + "[/dim]")
    err_console.print("  [dim]View all clients:  meridian client list[/dim]")
    err_console.print()


# -- Client Show --


def run_show(
    name: str,
    user: str = "",
    requested_server: str = "",
) -> None:
    """Display connection info for an existing client."""
    _validate_client_name(name)
    cluster = load_cluster()
    panel = make_panel(cluster)

    with panel:
        client = panel.get_user(name)
        if client is None:
            fail(
                f"Client '{name}' not found",
                hint="Check client name with: meridian client list",
                hint_type="user",
            )

        if is_json_mode():
            from meridian.console import json_output

            json_output(
                {
                    "client": {
                        "username": client.username,
                        "uuid": client.uuid,
                        "status": client.status,
                        "traffic_used": client.used_traffic_bytes,
                        "traffic_limit": client.traffic_limit_bytes,
                        "created_at": client.created_at,
                        "last_seen": client.online_at,
                        "subscription_url": panel.get_subscription_url(client.short_uuid),
                    }
                }
            )
            return

        # Print connection page URL + subscription
        page_url = _build_page_url(cluster, client.vless_uuid)
        _print_subscription(panel, client, page_url=page_url)

        # Print traffic stats
        err_console.print()
        err_console.print(f"  [bold]Status[/bold]    {_format_status(client.status)}")
        traffic = format_traffic(client.used_traffic_bytes, client.traffic_limit_bytes)
        err_console.print(f"  [bold]Traffic[/bold]   {traffic}")
        if client.online_at:
            err_console.print(f"  [bold]Last seen[/bold] {client.online_at}")

    err_console.print()
    if cluster.panel.url:
        err_console.print(f"  [dim]Remnawave panel:   {cluster.panel.display_url}[/dim]")
        if cluster.panel.admin_user:
            creds = f"{cluster.panel.admin_user} / {cluster.panel.admin_pass}"
            err_console.print(f"  [dim]                   {creds}[/dim]")
    err_console.print("  [dim]View all clients:  meridian client list[/dim]")
    err_console.print()


def run_list(
    user: str = "",
    requested_server: str = "",
) -> None:
    """List all clients from the Remnawave panel."""
    from rich.box import ROUNDED
    from rich.table import Table

    cluster = load_cluster()
    panel = make_panel(cluster)

    with panel:
        try:
            users = panel.list_users()
        except RemnawaveError as e:
            fail(
                f"Could not list clients: {e}",
                hint=e.hint or "Check panel connectivity",
                hint_type=e.hint_type,
            )

    from meridian.console import is_json_mode, json_output

    if is_json_mode():
        clients_data = [
            {
                "username": u.username,
                "uuid": u.uuid,
                "status": u.status,
                "traffic_used": u.used_traffic_bytes,
                "traffic_limit": u.traffic_limit_bytes,
                "created_at": u.created_at,
            }
            for u in users
        ]
        json_output({"clients": clients_data})
        return

    table = Table(
        title="Proxy Clients",
        show_lines=False,
        pad_edge=False,
        box=ROUNDED,
        padding=(0, 2),
    )
    table.add_column("Name", style="bold cyan")
    table.add_column("Status", justify="center")
    table.add_column("Traffic", style="dim")
    table.add_column("Last seen", style="dim")

    for u in users:
        table.add_row(
            u.username,
            _format_status(u.status),
            format_traffic(u.used_traffic_bytes, u.traffic_limit_bytes),
            u.online_at or "-",
        )

    count = len(users)
    suffix = "s" if count != 1 else ""

    err_console.print()
    err_console.print(table)
    err_console.print()
    err_console.print(f"  [dim]Total: {count} client{suffix}[/dim]")
    err_console.print()
    err_console.print("  [dim]Add: meridian client add NAME  |  Remove: meridian client remove NAME[/dim]")
    err_console.print()


# -- Client Remove --


def run_remove(
    name: str,
    user: str = "",
    requested_server: str = "",
    yes: bool = False,
) -> None:
    """Remove a client from the proxy cluster."""
    _validate_client_name(name)
    cluster = load_cluster()
    panel = make_panel(cluster)

    with panel:
        client = panel.get_user(name)
        if client is None:
            fail(
                f"Client '{name}' not found",
                hint="Check client name with: meridian client list",
                hint_type="user",
            )

        if not yes and not confirm(f"Remove client '{name}'?"):
            raise typer.Exit(1)

        success = panel.delete_user(client.uuid)
        if not success:
            fail(
                f"Could not remove client '{name}'",
                hint="The panel may be unreachable. Try again.",
                hint_type="system",
            )

        ok(f"Client '{name}' removed")

        # Clean up connection page files on server
        if client.vless_uuid and cluster.panel.server_ip:
            try:
                import shlex

                from meridian.ssh import ServerConnection

                with ServerConnection(
                    cluster.panel.server_ip,
                    user=cluster.panel.ssh_user or "root",
                    port=getattr(cluster.panel, "ssh_port", 22) or 22,
                ) as conn:
                    conn.run(
                        f"rm -rf /var/www/private/{shlex.quote(client.vless_uuid)}",
                        timeout=15,
                    )
            except Exception:
                pass  # Non-fatal

    err_console.print()
    err_console.print("  [dim]View all clients:  meridian client list[/dim]")
    err_console.print()
