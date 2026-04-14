"""Reusable provisioning operations — shared by imperative commands and reconciler.

Each function performs a complete operation (add node, remove relay, etc.)
without interactive prompts. The imperative command modules (node.py,
relay.py, client.py) handle user interaction then call these functions.
The reconciler executor calls them directly.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from meridian.cluster import ClusterConfig, NodeEntry, RelayEntry
from meridian.remnawave import MeridianPanel, RemnawaveError

logger = logging.getLogger("meridian.operations")


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------


def add_node(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    ip: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    name: str = "",
    domain: str = "",
    sni: str = "",
    harden: bool = True,
    warp: bool = False,
) -> NodeEntry:
    """Provision a new node and register it with the panel.

    Runs the full SSH provisioner pipeline, then configures the node via
    the panel REST API. Returns the new NodeEntry added to cluster.yml.
    """
    from meridian.commands.resolve import ResolvedServer, ensure_server_connection
    from meridian.commands.setup import _run_provisioner, _setup_new_node
    from meridian.config import DEFAULT_SNI
    from meridian.ssh import ServerConnection

    effective_sni = sni or DEFAULT_SNI

    # Establish SSH connection
    resolved = ResolvedServer(ip=ip, user=ssh_user, port=ssh_port, conn=ServerConnection(ip, ssh_user, port=ssh_port))
    ensure_server_connection(resolved)

    # Compute deterministic port layout
    ip_hash = int(hashlib.sha256(ip.encode()).hexdigest()[:8], 16)
    xhttp_port = 30000 + (ip_hash % 10000)
    reality_port = 10000 + ip_hash % 1000
    wss_port = 20000 + (ip_hash % 10000)
    xhttp_path = secrets.token_hex(8)
    ws_path = secrets.token_hex(8)

    # SSH provisioner pipeline (OS hardening, Docker, nginx, TLS)
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

    # Panel API: register node, deploy container, create hosts
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

    # Return the newly added node
    node = cluster.find_node(ip)
    if node is None:
        raise RuntimeError(f"Node {ip} was provisioned but not found in cluster config")
    return node


def update_node(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    ip: str,
    sni: str | None = None,
    domain: str | None = None,
    warp: bool = False,
) -> None:
    """Redeploy an existing node with updated configuration.

    Calls the existing _setup_redeploy() flow from setup.py.
    Uses None as sentinel for "not specified" (keep current).
    Empty string means "clear to default/empty".
    """
    from meridian.commands.resolve import ResolvedServer
    from meridian.commands.setup import _setup_redeploy
    from meridian.ssh import ServerConnection

    node = cluster.find_node(ip)
    if node is None:
        raise ValueError(f"Node {ip} not found in cluster")

    conn = ServerConnection(ip, node.ssh_user, port=node.ssh_port)
    resolved = ResolvedServer(ip=ip, user=node.ssh_user, port=node.ssh_port, conn=conn)

    # Compute port layout (same scheme as deploy)
    ip_hash = int(hashlib.sha256(ip.encode()).hexdigest()[:8], 16)
    xhttp_port = 30000 + (ip_hash % 10000)
    reality_port = 10000 + ip_hash % 1000
    wss_port = 20000 + (ip_hash % 10000)

    # None = keep current, "" = clear to empty/default
    effective_domain = domain if domain is not None else node.domain
    effective_sni = sni if sni is not None else node.sni

    from meridian import __version__

    _setup_redeploy(
        resolved=resolved,
        cluster=cluster,
        domain=effective_domain,
        sni=effective_sni,
        reality_port=reality_port,
        xhttp_port=xhttp_port,
        wss_port=wss_port,
        version=__version__,
        warp=warp,
        xhttp_path=node.xhttp_path,
        ws_path=node.ws_path,
    )


def remove_node(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    node_ip: str,
    force: bool = False,
) -> None:
    """Deregister a node from the panel and remove from cluster.yml."""
    node = cluster.find_node(node_ip)
    if node is None:
        raise ValueError(f"Node {node_ip} not found in cluster")

    if node.is_panel_host:
        raise ValueError("Cannot remove the panel node — use meridian teardown instead")

    # Guard: check for dependent relays
    dependent_relays = [r for r in cluster.relays if r.exit_node_ip == node.ip]
    if dependent_relays and not force:
        relay_names = ", ".join(r.name or r.ip for r in dependent_relays)
        raise ValueError(f"Cannot remove node {node.ip} — relays depend on it: {relay_names}")

    # Disable + delete in panel
    if node.uuid:
        try:
            panel.disable_node(node.uuid)
        except RemnawaveError:
            logger.warning("Could not disable node %s in panel", node.ip)
        try:
            panel.delete_node(node.uuid)
        except RemnawaveError as e:
            logger.warning("Could not delete node %s from panel: %s", node.ip, e)

    cluster.nodes = [n for n in cluster.nodes if n.ip != node.ip]
    cluster.save()


# ---------------------------------------------------------------------------
# Relay operations
# ---------------------------------------------------------------------------


def add_relay(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    relay_ip: str,
    exit_node_ip: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    name: str = "",
    sni: str = "",
    port: int = 443,
) -> RelayEntry:
    """Provision a relay and register host entries in the panel.

    Runs the Realm TCP forwarder provisioner on the relay server,
    creates Remnawave Host entries, and configures nginx SNI routing
    on the exit node.
    """
    from meridian.commands.resolve import ResolvedServer, ensure_server_connection
    from meridian.config import DEFAULT_SNI
    from meridian.ssh import ServerConnection

    effective_sni = sni or DEFAULT_SNI
    relay_name = name or relay_ip

    # Find exit node
    exit_node = cluster.find_node(exit_node_ip)
    if exit_node is None:
        raise ValueError(f"Exit node {exit_node_ip} not found in cluster")

    # SSH connections
    relay_conn = ServerConnection(relay_ip, ssh_user, port=ssh_port)
    relay_resolved = ResolvedServer(ip=relay_ip, user=ssh_user, port=ssh_port, conn=relay_conn)
    ensure_server_connection(relay_resolved)

    exit_conn = ServerConnection(exit_node.ip, exit_node.ssh_user, port=exit_node.ssh_port)

    # Run Realm provisioner
    from meridian.provision.relay import RelayContext, build_relay_steps
    from meridian.provision.steps import Provisioner

    relay_ctx = RelayContext(
        relay_ip=relay_ip,
        exit_ip=exit_node.ip,
        exit_port=port,
        listen_port=port,
    )
    steps = build_relay_steps(relay_ctx)
    provisioner = Provisioner(steps)
    results = provisioner.run(relay_conn, relay_ctx)
    if any(r.status == "failed" for r in results):
        raise RuntimeError(f"Relay provisioning failed on {relay_ip}")

    # Create host entries in panel
    host_uuids: dict[str, str] = {}
    from meridian.cluster import InboundRef

    for key, ref in cluster.inbounds.items():
        if not isinstance(ref, InboundRef) or not ref.uuid:
            continue
        remark = f"{key}-relay-{relay_name}"
        try:
            existing = panel.find_host_by_remark(remark)
            if existing:
                host_uuids[key] = existing.uuid
                continue
            host = panel.create_host(
                remark=remark,
                address=relay_ip,
                port=port,
                config_profile_uuid=cluster.config_profile_uuid,
                inbound_uuid=ref.uuid,
                sni=effective_sni,
            )
            host_uuids[key] = host.uuid
        except RemnawaveError as e:
            logger.warning("Could not create relay host %s: %s", remark, e)

    # Configure nginx SNI on exit node
    from meridian.commands.relay import _deploy_relay_nginx

    _deploy_relay_nginx(exit_conn, effective_sni, relay_ip, relay_name)

    # Save relay to cluster
    relay = RelayEntry(
        ip=relay_ip,
        name=relay_name,
        port=port,
        exit_node_ip=exit_node.ip,
        host_uuids=host_uuids,
        sni=effective_sni,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
    )
    cluster.relays.append(relay)
    cluster.save()

    return relay


def remove_relay(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    relay_ip: str,
) -> None:
    """Remove a relay: delete hosts, clean up nginx, remove from cluster.yml."""
    relay = cluster.find_relay(relay_ip)
    if relay is None:
        raise ValueError(f"Relay {relay_ip} not found in cluster")

    # Delete host entries from panel
    for key, host_uuid in relay.host_uuids.items():
        if host_uuid:
            try:
                panel.delete_host(host_uuid)
            except RemnawaveError as e:
                logger.warning("Could not delete relay host %s: %s", key, e)

    # Clean up nginx on exit node (best-effort)
    exit_node = cluster.find_node(relay.exit_node_ip)
    if exit_node:
        try:
            from meridian.ssh import ServerConnection

            exit_conn = ServerConnection(exit_node.ip, exit_node.ssh_user, port=exit_node.ssh_port)
            from meridian.commands.relay import _remove_relay_nginx

            _remove_relay_nginx(exit_conn, relay)
        except Exception as e:
            logger.warning("Could not clean up nginx for relay %s: %s", relay_ip, e)

    cluster.relays = [r for r in cluster.relays if r.ip != relay_ip]
    cluster.save()


# ---------------------------------------------------------------------------
# Client operations
# ---------------------------------------------------------------------------


def add_client(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    name: str,
) -> Any:
    """Create a client in the panel."""
    squad_uuids = [cluster.squad_uuid] if cluster.squad_uuid else None
    return panel.create_user(name, squad_uuids=squad_uuids)


def remove_client(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    name: str,
) -> bool:
    """Delete a client from the panel."""
    user = panel.get_user(name)
    if user and user.uuid:
        return panel.delete_user(user.uuid)
    return False
