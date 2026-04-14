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

    # Return the newly added node, applying desired name if provided
    node = cluster.find_node(ip)
    if node is None:
        raise RuntimeError(f"Node {ip} was provisioned but not found in cluster config")

    # _setup_new_node uses "domain or ip" as name. Override with desired name.
    if name and name != node.name:
        node.name = name
        if node.uuid:
            try:
                panel.update_node_name(node.uuid, name)
            except RemnawaveError as e:
                logger.warning("Could not set node name in panel: %s", e)
        cluster.save()

    return node


def update_node(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    ip: str,
    name: str | None = None,
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

    # Save old values for rollback if redeploy fails
    old_name, old_sni, old_domain, old_warp = node.name, node.sni, node.domain, node.warp

    # Update metadata before redeploy so _setup_redeploy reads new values.
    # None = keep current, "" = clear to empty/default.
    if name is not None:
        node.name = name
    if sni is not None:
        node.sni = sni
    if domain is not None:
        node.domain = domain
    node.warp = warp

    from meridian import __version__

    try:
        _setup_redeploy(
            resolved=resolved,
            cluster=cluster,
            domain=node.domain,
            sni=node.sni,
            reality_port=reality_port,
            xhttp_port=xhttp_port,
            wss_port=wss_port,
            version=__version__,
            warp=warp,
            xhttp_path=node.xhttp_path,
            ws_path=node.ws_path,
        )
    except Exception:
        # Rollback metadata on failure so cluster.yml stays accurate
        node.name, node.sni, node.domain, node.warp = old_name, old_sni, old_domain, old_warp
        raise

    # Update name in panel after successful redeploy
    if name is not None and name != old_name and node.uuid:
        try:
            panel.update_node_name(node.uuid, name)
        except RemnawaveError as e:
            logger.warning("Could not update node name in panel: %s", e)


def remove_node(
    cluster: ClusterConfig,
    panel: MeridianPanel,
    *,
    node_ip: str,
    force: bool = False,
) -> None:
    """Deregister a node from the panel and remove from cluster.yml.

    Handles both cluster-tracked nodes (in cluster.yml) and panel-only
    nodes (registered in panel but not in local config — e.g. stale or
    manually added nodes).
    """
    node = cluster.find_node(node_ip)

    if node is not None:
        if node.is_panel_host:
            raise ValueError("Cannot remove the panel node — use meridian teardown instead")

        # Guard: check for dependent relays
        dependent_relays = [r for r in cluster.relays if r.exit_node_ip == node.ip]
        if dependent_relays and not force:
            relay_names = ", ".join(r.name or r.ip for r in dependent_relays)
            raise ValueError(f"Cannot remove node {node.ip} — relays depend on it: {relay_names}")

    # Find node UUID — from cluster.yml or panel API
    node_uuid = node.uuid if node else ""
    if not node_uuid:
        # Panel-only node: look up by address
        api_node = panel.find_node_by_address(node_ip)
        if api_node:
            node_uuid = api_node.uuid

    # Disable + delete in panel
    if node_uuid:
        try:
            panel.disable_node(node_uuid)
        except RemnawaveError:
            logger.warning("Could not disable node %s in panel", node_ip)
        try:
            panel.delete_node(node_uuid)
        except RemnawaveError as e:
            logger.warning("Could not delete node %s from panel: %s", node_ip, e)

    # Remove from cluster.yml (no-op if panel-only node)
    cluster.nodes = [n for n in cluster.nodes if n.ip != node_ip]
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

    Reuses the same functions as the imperative ``meridian relay deploy``:
    Realm provisioner, ``_create_relay_hosts()``, ``_deploy_relay_nginx()``,
    and ``_save_relay_local()``.
    """
    from meridian.commands.relay import (
        _create_relay_hosts,
        _deploy_relay_nginx,
        _save_relay_local,
    )
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

    # Create host entries — uses the same function as imperative relay deploy
    # (creates REALITY + XHTTP hosts with correct security_layer/fingerprint)
    host_uuids = _create_relay_hosts(panel, cluster, relay_ip, port, effective_sni, relay_name)
    if not host_uuids:
        raise RuntimeError(f"Relay {relay_ip}: no panel hosts created")

    # Configure nginx SNI on exit node — only when relay SNI differs from
    # exit node's own SNI (same guard as imperative relay deploy).
    # Deploying nginx with the same SNI would hijack the exit node's Reality routing.
    if effective_sni and effective_sni != (exit_node.sni or ""):
        if not _deploy_relay_nginx(exit_conn, effective_sni, relay_ip, relay_name):
            raise RuntimeError(f"Relay {relay_ip}: nginx configuration failed on exit node")

    # Save local relay metadata (same as imperative path)
    _save_relay_local(relay_ip, exit_node.ip, port, port)

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
    """Remove a relay: delete hosts, stop Realm, clean nginx, remove from cluster.yml.

    Reuses the same functions as the imperative ``meridian relay remove``.
    """
    from meridian.commands.relay import _delete_relay_hosts, _remove_relay_nginx
    from meridian.config import RELAY_SERVICE_NAME, sanitize_ip_for_path
    from meridian.ssh import ServerConnection

    relay = cluster.find_relay(relay_ip)
    if relay is None:
        raise ValueError(f"Relay {relay_ip} not found in cluster")

    # Delete host entries from panel (same function as imperative path)
    _delete_relay_hosts(panel, relay)

    # Clean up nginx on exit node (best-effort)
    exit_node = cluster.find_node(relay.exit_node_ip)
    if exit_node:
        try:
            exit_conn = ServerConnection(exit_node.ip, exit_node.ssh_user, port=exit_node.ssh_port)
            _remove_relay_nginx(exit_conn, relay)
        except Exception as e:
            logger.warning("Could not clean up nginx for relay %s: %s", relay_ip, e)

    # Stop Realm service on relay host (same as imperative path)
    try:
        relay_conn = ServerConnection(relay_ip, relay.ssh_user, port=relay.ssh_port)
        relay_conn.run(f"systemctl stop {RELAY_SERVICE_NAME} 2>/dev/null", timeout=15)
        relay_conn.run(f"systemctl disable {RELAY_SERVICE_NAME} 2>/dev/null", timeout=10)
    except Exception as e:
        logger.warning("Could not stop relay service on %s: %s", relay_ip, e)

    # Remove from cluster.yml
    cluster.relays = [r for r in cluster.relays if r.ip != relay_ip]
    cluster.save()

    # Clean local relay metadata
    from meridian.config import CREDS_BASE

    relay_file = CREDS_BASE / sanitize_ip_for_path(relay_ip) / "relay.yml"
    if relay_file.exists():
        relay_file.unlink()


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
