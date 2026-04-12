"""Node management -- add, list, check, remove proxy nodes in the fleet.

Nodes are servers running Remnawave node + Xray. All node state is
tracked in the panel database; cluster.yml stores topology for local
reference and SSH access.
"""

from __future__ import annotations

import hashlib
import secrets

from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.console import confirm, err_console, fail, info, ok, warn
from meridian.remnawave import RemnawaveError

# -- Node Add --


def run_add(
    ip: str,
    name: str = "",
    user: str = "root",
    ssh_port: int = 22,
    sni: str = "",
    domain: str = "",
    harden: bool = True,
    yes: bool = False,
) -> None:
    """Provision and add a new node to the fleet."""
    from meridian.commands.resolve import ensure_server_connection, resolve_server
    from meridian.commands.setup import (
        DEFAULT_SNI,
        _run_provisioner,
        _setup_new_node,
    )

    if not ip:
        fail("Node IP address is required", hint="Usage: meridian node add IP", hint_type="user")

    cluster = load_cluster()

    # Check for duplicate
    existing = cluster.find_node(ip)
    if existing is not None:
        fail(
            f"Node {ip} already exists in cluster",
            hint=f"Use: meridian deploy {ip} to redeploy",
            hint_type="user",
        )

    # Resolve and connect
    resolved = resolve_server(ip, user=user, port=ssh_port)
    ensure_server_connection(resolved)

    node_name = name or ip
    effective_sni = sni or DEFAULT_SNI

    info(f"Adding node {resolved.ip} ({node_name})...")

    if not yes:
        confirm(f"Provision and add node at {resolved.ip}?")

    # Compute port layout (same scheme as deploy)
    ip_hash = int(hashlib.sha256(resolved.ip.encode()).hexdigest()[:8], 16)
    xhttp_port = 30000 + (ip_hash % 10000)
    reality_port = 10000 + ip_hash % 1000
    wss_port = 20000 + (ip_hash % 10000)

    # Generate paths
    xhttp_path = secrets.token_hex(8)
    ws_path = secrets.token_hex(8)

    # Run SSH provisioner pipeline (OS hardening, Docker, nginx, TLS)
    _run_provisioner(
        resolved=resolved,
        cluster=cluster,
        domain=domain,
        sni=effective_sni,
        harden=harden,
        is_panel_host=False,
        secret_path=cluster.panel.secret_path,
        xhttp_port=xhttp_port,
        reality_port=reality_port,
        wss_port=wss_port,
        xhttp_path=xhttp_path,
        ws_path=ws_path,
    )

    # Configure via panel API (register node, deploy container, create hosts)
    from meridian import __version__

    _setup_new_node(
        resolved=resolved,
        cluster=cluster,
        domain=domain,
        sni=effective_sni,
        reality_port=reality_port,
        xhttp_port=xhttp_port,
        wss_port=wss_port,
        version=__version__,
        xhttp_path=xhttp_path,
        ws_path=ws_path,
    )

    ok(f"Node {resolved.ip} provisioned and added to cluster")

    err_console.print()
    err_console.print("  [dim]List nodes:     meridian node list[/dim]")
    err_console.print("  [dim]Fleet status:   meridian fleet status[/dim]")
    err_console.print()


# -- Node List --


def run_list() -> None:
    """List all nodes with health status from the panel."""
    from rich.box import ROUNDED
    from rich.table import Table

    cluster = load_cluster()
    panel = make_panel(cluster)

    with panel:
        try:
            api_nodes = panel.list_nodes()
        except RemnawaveError as e:
            fail(
                f"Could not query nodes: {e}",
                hint=e.hint or "Check panel connectivity",
                hint_type=e.hint_type,
            )

    # Index API nodes by UUID for quick lookup
    api_by_uuid = {n.uuid: n for n in api_nodes}

    table = Table(
        title="Proxy Nodes",
        show_lines=False,
        pad_edge=False,
        box=ROUNDED,
        padding=(0, 2),
    )
    table.add_column("IP", style="bold cyan")
    table.add_column("Name", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Xray", style="dim")
    table.add_column("Traffic", style="dim")

    for node in cluster.nodes:
        api_node = api_by_uuid.get(node.uuid)
        if api_node:
            if api_node.is_connected:
                status = "[green]connected[/green]"
            elif api_node.is_disabled:
                status = "[dim]disabled[/dim]"
            else:
                status = "[red]disconnected[/red]"
            xray = api_node.xray_version or "-"
            traffic = format_traffic(api_node.traffic_used)
        else:
            status = "[dim]unknown[/dim]"
            xray = "-"
            traffic = "-"

        label = node.name or node.ip
        if node.is_panel_host:
            label += " [dim](panel)[/dim]"

        table.add_row(node.ip, label, status, xray, traffic)

    # Show API-only nodes not in cluster config
    cluster_uuids = {n.uuid for n in cluster.nodes}
    for api_node in api_nodes:
        if api_node.uuid and api_node.uuid not in cluster_uuids:
            status = "[green]connected[/green]" if api_node.is_connected else "[red]disconnected[/red]"
            table.add_row(
                api_node.address,
                f"{api_node.name} [yellow](untracked)[/yellow]",
                status,
                api_node.xray_version or "-",
                format_traffic(api_node.traffic_used),
            )

    err_console.print()
    err_console.print(table)
    n_cluster = len(cluster.nodes)
    n_panel = len(api_nodes)
    err_console.print(f"\n  [dim]Total: {n_cluster} node(s) in cluster, {n_panel} registered in panel[/dim]")
    err_console.print()


# -- Node Remove --


def run_remove(ip_or_name: str, yes: bool = False, force: bool = False) -> None:
    """Remove a node from the fleet."""
    if not ip_or_name:
        fail("Node IP or name is required", hint="Usage: meridian node remove IP_OR_NAME", hint_type="user")

    cluster = load_cluster()

    node = cluster.find_node(ip_or_name)
    if node is None:
        fail(
            f"Node '{ip_or_name}' not found",
            hint="Check node list with: meridian node list",
            hint_type="user",
        )

    if node.is_panel_host:
        fail(
            "Cannot remove the panel node",
            hint="The panel runs on this node. Use 'meridian teardown' instead.",
            hint_type="user",
        )

    # Guard: check for relays that depend on this node as their exit
    dependent_relays = [r for r in cluster.relays if r.exit_node_ip == node.ip]
    if dependent_relays:
        relay_names = ", ".join(r.name or r.ip for r in dependent_relays)
        if not force:
            fail(
                f"Cannot remove node {node.ip} — {len(dependent_relays)} relay(s) depend on it: {relay_names}",
                hint="Remove relays first, or use --force to remove anyway",
                hint_type="user",
            )
        else:
            warn(f"Force-removing node with {len(dependent_relays)} dependent relay(s): {relay_names}")

    if not yes:
        confirm(f"Remove node {node.ip} ({node.name or 'unnamed'})?")

    panel = make_panel(cluster)
    with panel:
        if node.uuid:
            try:
                panel.disable_node(node.uuid)
                info("Node disabled in panel")
            except RemnawaveError:
                warn("Could not disable node in panel (may already be disabled)")

            try:
                panel.delete_node(node.uuid)
                ok("Node removed from panel")
            except RemnawaveError as e:
                warn(f"Could not delete node from panel: {e}")

    # TODO: Optionally SSH in and teardown containers:
    #   conn = ServerConnection(node.ip, user=node.ssh_user, port=node.ssh_port)
    #   conn.run("docker compose down -v", ...)

    cluster.nodes = [n for n in cluster.nodes if n.ip != node.ip]
    cluster.save()

    ok(f"Node {node.ip} removed from cluster")

    err_console.print()
    err_console.print("  [dim]List nodes:   meridian node list[/dim]")
    err_console.print()
