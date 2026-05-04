"""Fleet status -- overview of all nodes, relays, and users.

Single command that shows the health of the entire Meridian cluster
at a glance: panel connectivity, node status, relay reachability, user count.
"""

from __future__ import annotations

import socket

from meridian.cluster import DesiredNode, DesiredRelay, NodeEntry, RelayEntry
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


def _node_api_status(api_node: object | None) -> str:
    if not api_node:
        return "unknown"
    if getattr(api_node, "is_connected", False):
        return "connected"
    if getattr(api_node, "is_disabled", False):
        return "disabled"
    return "disconnected"


def _node_protocols(node: NodeEntry) -> list[str]:
    protocols = ["reality"]
    if node.xhttp_path:
        protocols.append("xhttp")
    if node.domain and node.ws_path:
        protocols.append("wss")
    return protocols


def _desired_node_key(desired: DesiredNode) -> str:
    return desired.host


def _desired_relay_key(desired: DesiredRelay) -> str:
    return desired.host


def _node_desired(node: NodeEntry, desired_nodes: list[DesiredNode] | None) -> bool | None:
    if desired_nodes is None:
        return None
    return any(node.ip == d.host for d in desired_nodes)


def _relay_desired(relay: RelayEntry, desired_relays: list[DesiredRelay] | None) -> bool | None:
    if desired_relays is None:
        return None
    return any(relay.ip == d.host for d in desired_relays)


# -- Fleet Inventory --


def run_inventory() -> None:
    """Show the configured fleet inventory without exposing secrets."""
    cluster = load_cluster()
    panel_url = cluster.panel.display_url or cluster.panel.url
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

    api_by_uuid = {n.uuid: n for n in api_nodes}
    desired_node_keys = {_desired_node_key(d) for d in cluster.desired_nodes or [] if _desired_node_key(d)}
    desired_relay_keys = {_desired_relay_key(d) for d in cluster.desired_relays or [] if _desired_relay_key(d)}
    actual_node_keys = {n.ip for n in cluster.nodes if n.ip}
    actual_relay_keys = {r.ip for r in cluster.relays if r.ip}

    nodes_json = []
    for node in cluster.nodes:
        api_node = api_by_uuid.get(node.uuid)
        nodes_json.append(
            {
                "ip": node.ip,
                "name": node.name,
                "uuid": node.uuid,
                "role": "panel+node" if node.is_panel_host else "node",
                "ssh_user": node.ssh_user,
                "ssh_port": node.ssh_port,
                "domain": node.domain,
                "sni": node.sni,
                "protocols": _node_protocols(node),
                "desired": _node_desired(node, cluster.desired_nodes),
                "panel_status": _node_api_status(api_node),
                "xray_version": api_node.xray_version if api_node else "",
            }
        )

    relays_json = []
    for relay in cluster.relays:
        exit_node = cluster.find_node(relay.exit_node_ip)
        relays_json.append(
            {
                "ip": relay.ip,
                "name": relay.name,
                "role": "relay",
                "port": relay.port,
                "ssh_user": relay.ssh_user,
                "ssh_port": relay.ssh_port,
                "exit_node_ip": relay.exit_node_ip,
                "exit_node_name": exit_node.name if exit_node else "",
                "sni": relay.sni,
                "host_count": len(relay.host_uuids),
                "desired": _relay_desired(relay, cluster.desired_relays),
            }
        )

    desired_nodes_json = [
        {
            "host": d.host,
            "name": d.name,
            "ssh_user": d.ssh_user,
            "ssh_port": d.ssh_port,
            "domain": d.domain,
            "sni": d.sni,
            "warp": d.warp,
            "present": bool(d.host and d.host in actual_node_keys),
        }
        for d in cluster.desired_nodes or []
    ]
    desired_relays_json = [
        {
            "host": d.host,
            "name": d.name,
            "ssh_user": d.ssh_user,
            "ssh_port": d.ssh_port,
            "exit_node": d.exit_node,
            "sni": d.sni,
            "present": bool(d.host and d.host in actual_relay_keys),
        }
        for d in cluster.desired_relays or []
    ]
    total_pending = len(desired_node_keys - actual_node_keys) + len(desired_relay_keys - actual_relay_keys)

    data = {
        "panel": {
            "url": panel_url,
            "server_ip": cluster.panel.server_ip,
            "ssh_user": cluster.panel.ssh_user,
            "ssh_port": cluster.panel.ssh_port,
            "healthy": panel_ok,
            "deployed_with": cluster.panel.deployed_with,
            "subscription_page": {
                "enabled": bool(cluster.subscription_page and cluster.subscription_page.enabled),
                "path": cluster.subscription_page.path if cluster.subscription_page else "",
            },
        },
        "summary": {
            "nodes": len(cluster.nodes),
            "relays": len(cluster.relays),
            "desired_nodes": len(cluster.desired_nodes or []),
            "desired_relays": len(cluster.desired_relays or []),
            "unapplied_desired_nodes": len(desired_node_keys - actual_node_keys),
            "unapplied_desired_relays": len(desired_relay_keys - actual_relay_keys),
        },
        "nodes": nodes_json,
        "relays": relays_json,
        "desired_nodes": desired_nodes_json,
        "desired_relays": desired_relays_json,
    }

    if is_json_mode():
        json_output(data)
        return

    err_console.print()
    status = "[green]healthy[/green]" if panel_ok else "[red]UNREACHABLE[/red]"
    err_console.print(f"  [bold]Panel[/bold]   {panel_url}  {status}")
    if cluster.panel.server_ip:
        err_console.print(
            f"            SSH {cluster.panel.ssh_user}@{cluster.panel.server_ip}:{cluster.panel.ssh_port}"
        )

    err_console.print()
    err_console.print("  [bold]Nodes[/bold]")
    if not nodes_json:
        err_console.print("    [dim]none[/dim]")
    for display_node in nodes_json:
        desired = (
            ""
            if display_node["desired"] is None
            else "  desired"
            if display_node["desired"]
            else "  [yellow]extra[/yellow]"
        )
        domain = f"  domain={display_node['domain']}" if display_node["domain"] else ""
        err_console.print(
            f"    {display_node['ip']}  {display_node['name'] or '-'}  {display_node['role']}  "
            f"{display_node['panel_status']}{domain}{desired}"
        )

    err_console.print()
    err_console.print("  [bold]Relays[/bold]")
    if not relays_json:
        err_console.print("    [dim]none[/dim]")
    for display_relay in relays_json:
        target = display_relay["exit_node_name"] or display_relay["exit_node_ip"]
        desired = (
            ""
            if display_relay["desired"] is None
            else "  desired"
            if display_relay["desired"]
            else "  [yellow]extra[/yellow]"
        )
        err_console.print(
            f"    {display_relay['ip']}  {display_relay['name'] or '-'}  :{display_relay['port']} -> {target}{desired}"
        )

    if desired_node_keys or desired_relay_keys:
        err_console.print()
        err_console.print(
            "  [bold]Desired[/bold] "
            f"{len(desired_node_keys)} node(s), {len(desired_relay_keys)} relay(s); "
            f"{total_pending} pending"
        )
    err_console.print()


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
