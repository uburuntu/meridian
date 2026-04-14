"""Desired and actual state snapshots for the reconciler.

``DesiredState`` is built from ``cluster.yml`` v2 desired-state fields.
``ActualState`` is fetched from the Remnawave panel API.
Both are plain dataclasses — no I/O in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DesiredNodeState:
    """A node that should exist."""

    host: str = ""
    name: str = ""
    ssh_user: str = "root"
    ssh_port: int = 22
    domain: str = ""
    sni: str = ""
    warp: bool = False


@dataclass
class DesiredRelayState:
    """A relay that should exist."""

    host: str = ""
    name: str = ""
    exit_node: str = ""
    ssh_user: str = "root"
    ssh_port: int = 22


@dataclass
class DesiredState:
    """What the cluster should look like (from cluster.yml v2).

    The ``manage_*`` flags indicate whether each resource type is
    explicitly declared. An empty list with ``manage_*=False`` means
    "don't touch this resource type" (not "delete everything").
    """

    nodes: list[DesiredNodeState] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    relays: list[DesiredRelayState] = field(default_factory=list)
    subscription_page_enabled: bool = False
    manage_nodes: bool = False
    manage_clients: bool = False
    manage_relays: bool = False


@dataclass
class ActualNodeState:
    """A node that currently exists in the panel."""

    host: str = ""
    name: str = ""
    uuid: str = ""
    is_connected: bool = False
    sni: str = ""
    domain: str = ""
    warp: bool = False


@dataclass
class ActualRelayState:
    """A relay that currently exists."""

    host: str = ""
    name: str = ""
    exit_node_ip: str = ""


@dataclass
class ActualState:
    """What the cluster actually looks like (from panel API + cluster.yml)."""

    nodes: list[ActualNodeState] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    relays: list[ActualRelayState] = field(default_factory=list)
    subscription_page_running: bool = False


def build_desired_state(cluster: object) -> DesiredState:
    """Build DesiredState from a ClusterConfig.

    Reads the v2 desired-state fields (desired_nodes, desired_clients,
    desired_relays, subscription_page).
    """
    from meridian.cluster import ClusterConfig

    if not isinstance(cluster, ClusterConfig):
        return DesiredState()

    nodes = [
        DesiredNodeState(
            host=dn.host,
            name=dn.name,
            ssh_user=dn.ssh_user,
            ssh_port=dn.ssh_port,
            domain=dn.domain,
            sni=dn.sni,
            warp=dn.warp,
        )
        for dn in (cluster.desired_nodes or [])
    ]

    relays = [
        DesiredRelayState(
            host=dr.host,
            name=dr.name,
            exit_node=dr.exit_node,
            ssh_user=dr.ssh_user,
            ssh_port=dr.ssh_port,
        )
        for dr in (cluster.desired_relays or [])
    ]

    sub_enabled = cluster.subscription_page.enabled if cluster.subscription_page else True

    # manage_* is True when the section is present (even if empty list).
    # desired_nodes=None means "not declared" → don't manage.
    # desired_nodes=[] means "declared, want zero" → manage (delete all).
    return DesiredState(
        nodes=nodes,
        clients=list(cluster.desired_clients) if cluster.desired_clients is not None else [],
        relays=relays,
        subscription_page_enabled=sub_enabled,
        manage_nodes=cluster.desired_nodes is not None,
        manage_clients=cluster.desired_clients is not None,
        manage_relays=cluster.desired_relays is not None,
    )


def build_actual_state(
    cluster: object,
    panel: object,
    panel_conn: object | None = None,
) -> ActualState:
    """Build ActualState from the panel API (live infrastructure).

    Nodes and clients are fetched from the panel API — the authoritative
    source. Relays come from cluster.yml (not tracked in the panel).

    Args:
        panel_conn: Optional SSH connection to the panel host. When
            provided, subscription page status is checked via
            ``docker inspect`` for live drift detection.
    """
    from meridian.cluster import ClusterConfig
    from meridian.remnawave import MeridianPanel

    if not isinstance(cluster, ClusterConfig) or not isinstance(panel, MeridianPanel):
        return ActualState()

    # Nodes: from panel API (live state) enriched with cluster.yml attributes.
    # Panel API provides connectivity; cluster.yml provides sni/domain/warp.
    #
    # Panel host nodes are registered under the Docker gateway IP (e.g. 172.17.0.1)
    # because the panel container can't reach 127.0.0.1 on the host. We map
    # these back to the public IP using cluster.yml so the diff works correctly.
    cluster_nodes_by_ip = {n.ip: n for n in cluster.nodes}
    # Build reverse map: panel API address → public IP (for Docker gateway nodes)
    api_addr_to_public_ip: dict[str, str] = {}
    for cn in cluster.nodes:
        # If a node's UUID matches an API node with a different address, map it
        api_addr_to_public_ip[cn.ip] = cn.ip  # identity for non-gateway nodes

    actual_nodes = []
    for n in panel.list_nodes():
        # Try to resolve Docker gateway address back to public IP
        public_ip = n.address
        for cn in cluster.nodes:
            if cn.uuid == n.uuid:
                public_ip = cn.ip
                break
        cn = cluster_nodes_by_ip.get(public_ip)
        actual_nodes.append(
            ActualNodeState(
                host=public_ip,
                name=n.name,
                uuid=n.uuid,
                is_connected=n.is_connected,
                sni=cn.sni if cn else "",
                domain=cn.domain if cn else "",
                warp=cn.warp if cn else False,
            )
        )

    # Clients: from panel API
    actual_clients = [u.username for u in panel.list_users()]

    # Relays: from cluster.yml (relays aren't tracked in the panel API)
    actual_relays = [
        ActualRelayState(
            host=r.ip,
            name=r.name,
            exit_node_ip=r.exit_node_ip,
        )
        for r in cluster.relays
    ]

    # Subscription page: check live container status via SSH when possible,
    # fall back to the deployment flag when SSH is not available.
    sub_running = False
    if panel_conn is not None:
        from meridian.ssh import ServerConnection

        if isinstance(panel_conn, ServerConnection):
            result = panel_conn.run(
                "docker inspect -f '{{.State.Running}}' remnawave-subscription-page 2>/dev/null",
                timeout=15,
            )
            sub_running = result.returncode == 0 and result.stdout.strip() == "true"
    else:
        # Fallback: trust the deployment flag from cluster.yml
        sub_page = cluster.subscription_page
        sub_running = bool(sub_page._extra.get("deployed", False)) if sub_page else False

    return ActualState(
        nodes=actual_nodes,
        clients=actual_clients,
        relays=actual_relays,
        subscription_page_running=sub_running,
    )
