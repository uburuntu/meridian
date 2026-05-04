"""Fleet status -- overview of all nodes, relays, and users.

Single command that shows the health of the entire Meridian cluster
at a glance: panel connectivity, node status, relay reachability, user count.
"""

from __future__ import annotations

import socket

from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.console import err_console, is_json_mode, warn
from meridian.core.fleet import FleetStatus, build_fleet_inventory, build_fleet_status
from meridian.core.models import Summary
from meridian.core.output import emit_json, envelope
from meridian.remnawave import RemnawaveError


def _check_relay_health(ip: str, port: int, timeout: float = 3.0) -> bool:
    """TCP connect check to verify relay is reachable."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


# -- Fleet Inventory --


def run_inventory() -> None:
    """Show the configured fleet inventory without exposing secrets."""
    cluster = load_cluster()
    panel_ok = False
    api_nodes = []

    try:
        panel = make_panel(cluster)
        with panel:
            panel_ok = panel.ping()
            if panel_ok:
                try:
                    api_nodes = panel.list_nodes()
                except RemnawaveError:
                    warn("Could not fetch node status from panel")
    except RemnawaveError:
        panel_ok = False

    inventory = build_fleet_inventory(cluster, panel_healthy=panel_ok, api_nodes=api_nodes)
    data = inventory.to_data()

    if is_json_mode():
        emit_json(
            envelope(
                command="fleet.inventory",
                data=data,
                summary=Summary(
                    text=inventory.summary.text,
                    changed=inventory.summary.pending > 0,
                    counts={
                        "nodes": inventory.summary.nodes,
                        "relays": inventory.summary.relays,
                        "pending": inventory.summary.pending,
                    },
                ),
                status="changed" if inventory.summary.pending else "ok",
            )
        )
        return

    err_console.print()
    status = "[green]healthy[/green]" if panel_ok else "[red]UNREACHABLE[/red]"
    err_console.print(f"  [bold]Panel[/bold]   {inventory.panel.url}  {status}")
    if cluster.panel.server_ip:
        err_console.print(
            f"            SSH {cluster.panel.ssh_user}@{cluster.panel.server_ip}:{cluster.panel.ssh_port}"
        )

    err_console.print()
    err_console.print("  [bold]Nodes[/bold]")
    if not inventory.nodes:
        err_console.print("    [dim]none[/dim]")
    for display_node in inventory.nodes:
        desired = (
            "" if display_node.desired is None else "  desired" if display_node.desired else "  [yellow]extra[/yellow]"
        )
        domain = f"  domain={display_node.domain}" if display_node.domain else ""
        err_console.print(
            f"    {display_node.ip}  {display_node.name or '-'}  {display_node.role}  "
            f"{display_node.panel_status}{domain}{desired}"
        )

    err_console.print()
    err_console.print("  [bold]Relays[/bold]")
    if not inventory.relays:
        err_console.print("    [dim]none[/dim]")
    for display_relay in inventory.relays:
        target = display_relay.exit_node_name or display_relay.exit_node_ip
        desired = (
            ""
            if display_relay.desired is None
            else "  desired"
            if display_relay.desired
            else "  [yellow]extra[/yellow]"
        )
        err_console.print(
            f"    {display_relay.ip}  {display_relay.name or '-'}  :{display_relay.port} -> {target}{desired}"
        )

    if inventory.summary.desired_nodes or inventory.summary.desired_relays:
        err_console.print()
        err_console.print(
            "  [bold]Desired[/bold] "
            f"{inventory.summary.desired_nodes} node(s), {inventory.summary.desired_relays} relay(s); "
            f"{inventory.summary.pending} pending"
        )
    err_console.print()


# -- Fleet Status --


def _render_status(status: FleetStatus) -> None:
    """Render fleet status for humans from the typed core result."""
    err_console.print()
    panel_state = "[green]healthy[/green]" if status.panel.healthy else "[red]UNREACHABLE[/red]"
    err_console.print(f"  [bold]Panel[/bold]   {status.panel.url} {panel_state}")

    if status.nodes:
        err_console.print()
        err_console.print("  [bold]Nodes[/bold]")

        for node in status.nodes:
            label = node.name or node.ip
            role = "  [dim](panel)[/dim]" if node.is_panel_host else ""

            if node.status == "connected":
                xray = f"  Xray {node.xray_version}" if node.xray_version else ""
                traffic = f"  {format_traffic(node.traffic_bytes)}" if node.traffic_bytes else ""
                err_console.print(f"    {node.ip}  {label}{role}  [green]connected[/green]{xray}{traffic}")
            elif node.status == "disabled":
                err_console.print(f"    {node.ip}  {label}{role}  [dim]disabled[/dim]")
            elif node.status == "disconnected":
                err_console.print(f"    {node.ip}  {label}{role}  [red]DISCONNECTED[/red]")
            else:
                err_console.print(f"    {node.ip}  {label}{role}  [dim]unknown[/dim]")

    if status.relays:
        err_console.print()
        err_console.print("  [bold]Relays[/bold]")

        for relay in status.relays:
            label = relay.name or relay.ip
            target_label = relay.exit_node_name or relay.exit_node_ip
            relay_state = "[green]healthy[/green]" if relay.healthy else "[red]UNREACHABLE[/red]"

            err_console.print(f"    {relay.ip}  {label} -> {target_label}  relay: {relay_state}")

    if status.users:
        err_console.print()
        parts = [f"{status.summary.active_users} active"]
        if status.summary.disabled_users:
            parts.append(f"{status.summary.disabled_users} disabled")
        if status.summary.other_users:
            parts.append(f"{status.summary.other_users} other")
        err_console.print(f"  [bold]Users[/bold]   {', '.join(parts)}")

    err_console.print()


def run_status() -> None:
    """Show fleet health overview: panel, nodes, relays, users."""
    cluster = load_cluster()
    panel = make_panel(cluster)
    panel_ok = False
    api_nodes = []
    api_users = []

    with panel:
        panel_ok = panel.ping()
        if not panel_ok and not is_json_mode():
            warn("Cannot reach panel API -- node and user data may be stale")

        if panel_ok:
            try:
                api_nodes = panel.list_nodes()
            except RemnawaveError:
                warn("Could not fetch node status from panel")
            try:
                api_users = panel.list_users()
            except RemnawaveError:
                pass

    relay_health = {(relay.ip, relay.port): _check_relay_health(relay.ip, relay.port) for relay in cluster.relays}
    status = build_fleet_status(
        cluster,
        panel_healthy=panel_ok,
        api_nodes=api_nodes,
        api_users=api_users,
        relay_health=relay_health,
    )

    if is_json_mode():
        emit_json(
            envelope(
                command="fleet.status",
                data=status.to_data(),
                summary=Summary(
                    text=status.summary.text,
                    changed=False,
                    counts={
                        "nodes": status.summary.nodes,
                        "relays": status.summary.relays,
                        "users": status.summary.users,
                        "unhealthy_relays": status.summary.unhealthy_relays,
                        "disconnected_nodes": status.summary.disconnected_nodes,
                        "disabled_nodes": status.summary.disabled_nodes,
                        "unknown_nodes": status.summary.unknown_nodes,
                    },
                ),
            )
        )
        return

    _render_status(status)
