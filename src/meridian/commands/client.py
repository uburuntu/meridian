"""Client management -- add, show, list, remove proxy clients.

All client state lives in Remnawave's database. No local proxy.yml,
no credential sync, no rollback. One API call per operation.
"""

from __future__ import annotations

import re

from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.console import confirm, err_console, fail, info, ok
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


def _print_subscription(panel: MeridianPanel, user: User) -> None:
    """Print subscription URL and QR code for a user."""
    from meridian.urls import generate_qr_terminal

    sub_url = panel.get_subscription_url(user.short_uuid)

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
            new_user = panel.create_user(name)
        except RemnawaveError as e:
            fail(
                f"Could not create client: {e}",
                hint=e.hint or "Check panel connectivity",
                hint_type=e.hint_type,
            )

        ok(f"Client '{name}' added")
        _print_subscription(panel, new_user)

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

        # Print subscription URL + QR
        _print_subscription(panel, client)

        # Print traffic stats
        err_console.print()
        err_console.print(f"  [bold]Status[/bold]    {_format_status(client.status)}")
        traffic = format_traffic(client.used_traffic_bytes, client.traffic_limit_bytes)
        err_console.print(f"  [bold]Traffic[/bold]   {traffic}")
        if client.online_at:
            err_console.print(f"  [bold]Last seen[/bold] {client.online_at}")

    err_console.print()
    err_console.print("  [dim]View all clients:  meridian client list[/dim]")
    err_console.print()


# -- Client List --


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

        confirm(f"Remove client '{name}'?")

        success = panel.delete_user(client.uuid)
        if not success:
            fail(
                f"Could not remove client '{name}'",
                hint="The panel may be unreachable. Try again.",
                hint_type="system",
            )

        ok(f"Client '{name}' removed")

    err_console.print()
    err_console.print("  [dim]View all clients:  meridian client list[/dim]")
    err_console.print()
