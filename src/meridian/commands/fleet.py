"""Fleet status -- overview of all nodes, relays, and users.

Single command that shows the health of the entire Meridian cluster
at a glance: panel connectivity, node status, relay reachability, user count.
"""

from __future__ import annotations

import socket

from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.console import err_console, is_json_mode, json_output, warn
from meridian.remnawave import RemnawaveError


def _check_relay_health(ip: str, port: int, timeout: float = 3.0) -> bool:
    """TCP connect check to verify relay is reachable."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


# -- Fleet Status --


def run_status() -> None:
    """Show fleet health overview: panel, nodes, relays, users."""
    cluster = load_cluster()
    panel = make_panel(cluster)

    # -- Panel health --
    err_console.print()
    panel_url = cluster.panel.display_url or cluster.panel.url
    with panel:
        panel_ok = panel.ping()
        if panel_ok:
            err_console.print(f"  [bold]Panel[/bold]   {panel_url} [green]healthy[/green]")
        else:
            err_console.print(f"  [bold]Panel[/bold]   {panel_url} [red]UNREACHABLE[/red]")
            warn("Cannot reach panel API -- node and user data may be stale")

        # -- Nodes --
        api_nodes = []
        if panel_ok:
            try:
                api_nodes = panel.list_nodes()
            except RemnawaveError:
                warn("Could not fetch node status from panel")

        api_by_uuid = {n.uuid: n for n in api_nodes}

        if cluster.nodes:
            err_console.print()
            err_console.print("  [bold]Nodes[/bold]")

            for node in cluster.nodes:
                api_node = api_by_uuid.get(node.uuid)
                label = node.name or node.ip
                role = "  [dim](panel)[/dim]" if node.is_panel_host else ""

                if api_node and api_node.is_connected:
                    xray = f"  Xray {api_node.xray_version}" if api_node.xray_version else ""
                    traffic = f"  {format_traffic(api_node.traffic_used)}" if api_node.traffic_used else ""
                    err_console.print(f"    {node.ip}  {label}{role}  [green]connected[/green]{xray}{traffic}")
                elif api_node and api_node.is_disabled:
                    err_console.print(f"    {node.ip}  {label}{role}  [dim]disabled[/dim]")
                elif api_node:
                    err_console.print(f"    {node.ip}  {label}{role}  [red]DISCONNECTED[/red]")
                else:
                    err_console.print(f"    {node.ip}  {label}{role}  [dim]unknown[/dim]")

        # -- Relays --
        if cluster.relays:
            err_console.print()
            err_console.print("  [bold]Relays[/bold]")

            for relay in cluster.relays:
                label = relay.name or relay.ip
                target_node = cluster.find_node(relay.exit_node_ip)
                target_label = target_node.name if target_node else relay.exit_node_ip

                healthy = _check_relay_health(relay.ip, relay.port)
                if healthy:
                    status = "[green]healthy[/green]"
                else:
                    status = "[red]UNREACHABLE[/red]"

                err_console.print(f"    {relay.ip}  {label} -> {target_label}  relay: {status}")

        # -- Users --
        users_data: list[dict] = []
        if panel_ok:
            try:
                users = panel.list_users()
                active = sum(1 for u in users if u.status.upper() == "ACTIVE")
                disabled = sum(1 for u in users if u.status.upper() == "DISABLED")
                other = len(users) - active - disabled
                users_data = [{"username": u.username, "status": u.status} for u in users]

                if not is_json_mode():
                    err_console.print()
                    parts = [f"{active} active"]
                    if disabled:
                        parts.append(f"{disabled} disabled")
                    if other:
                        parts.append(f"{other} other")
                    err_console.print(f"  [bold]Users[/bold]   {', '.join(parts)}")
            except RemnawaveError:
                pass

        # -- JSON output --
        if is_json_mode():
            nodes_json = []
            for node in cluster.nodes:
                api_node = api_by_uuid.get(node.uuid)
                nodes_json.append(
                    {
                        "ip": node.ip,
                        "name": node.name,
                        "uuid": node.uuid,
                        "is_panel_host": node.is_panel_host,
                        "status": (
                            "connected"
                            if api_node and api_node.is_connected
                            else "disabled"
                            if api_node and api_node.is_disabled
                            else "disconnected"
                            if api_node
                            else "unknown"
                        ),
                        "xray_version": api_node.xray_version if api_node else "",
                        "traffic_bytes": api_node.traffic_used if api_node else 0,
                    }
                )
            relays_json = []
            for relay in cluster.relays:
                relays_json.append(
                    {
                        "ip": relay.ip,
                        "name": relay.name,
                        "port": relay.port,
                        "exit_node_ip": relay.exit_node_ip,
                        "healthy": _check_relay_health(relay.ip, relay.port),
                    }
                )
            json_output(
                {
                    "panel": {"url": panel_url, "healthy": panel_ok},
                    "nodes": nodes_json,
                    "relays": relays_json,
                    "users": users_data,
                }
            )
            return

    err_console.print()
