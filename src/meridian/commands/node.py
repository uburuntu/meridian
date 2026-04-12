"""Node management -- add, list, remove proxy nodes in the fleet.

Nodes are servers running Remnawave node + Xray. All node state is
tracked in the panel database; cluster.yml stores topology for local
reference and SSH access.
"""

from __future__ import annotations

from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.cluster import ClusterConfig, NodeEntry
from meridian.console import confirm, err_console, fail, info, ok, warn
from meridian.remnawave import MeridianPanel, RemnawaveError


# -- Node Add --


def run_add(
    ip: str,
    name: str = "",
    user: str = "root",
    ssh_port: int = 22,
    sni: str = "",
    port: int = 2087,
) -> None:
    """Add a new node to the fleet."""
    if not ip:
        fail("Node IP address is required", hint="Usage: meridian node add IP", hint_type="user")

    cluster = load_cluster()

    # Check for duplicate
    existing = cluster.find_node(ip)
    if existing is not None:
        fail(f"Node {ip} already exists in cluster", hint="Use: meridian node list", hint_type="user")

    node_name = name or ip

    info(f"Adding node {ip} ({node_name})...")

    # TODO: SSH into the new server and run provisioner pipeline:
    #   conn = ServerConnection(ip, user=user, port=ssh_port)
    #   steps = build_node_steps(conn, ...)
    #   run_steps(steps)
    # This provisions OS hardening, Docker, and Remnawave node container.
    # For now, we assume the node is already provisioned and register it
    # with the panel API only.

    panel = make_panel(cluster)
    with panel:
        # Collect inbound UUIDs from cluster config
        inbound_uuids = [ref.uuid for ref in cluster.inbounds.values() if ref.uuid]

        # Register node with the panel
        try:
            creds = panel.create_node(
                name=node_name,
                address=ip,
                port=port,
                config_profile_uuid=cluster.config_profile_uuid,
                inbound_uuids=inbound_uuids or None,
            )
        except RemnawaveError as e:
            fail(
                f"Could not register node: {e}",
                hint=e.hint or "Check panel connectivity",
                hint_type=e.hint_type,
            )

        ok(f"Node registered with panel (uuid: {creds.uuid[:8]}...)")

        # TODO: Write SECRET_KEY to node's .env and restart container:
        #   conn.run(f"echo 'SECRET_KEY={shlex.quote(creds.secret_key)}' > ...")
        #   conn.run("docker compose restart remnawave-node")

        if creds.secret_key:
            info("Secret key obtained -- provision the node container to complete setup")

        # TODO: Create hosts for this node's IP
        #   panel.create_host(remark=..., address=ip, port=443, inbound_uuid=...)

    # Save to cluster config
    node_entry = NodeEntry(
        ip=ip,
        uuid=creds.uuid,
        name=node_name,
        ssh_user=user,
        ssh_port=ssh_port,
        sni=sni,
    )
    cluster.nodes.append(node_entry)
    cluster.save()

    ok(f"Node {ip} added to cluster")

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


def run_remove(ip_or_name: str, yes: bool = False) -> None:
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
