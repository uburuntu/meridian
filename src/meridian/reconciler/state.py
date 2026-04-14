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
    protocols: list[str] = field(default_factory=list)
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
    """What the cluster should look like (from cluster.yml v2)."""

    nodes: list[DesiredNodeState] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    relays: list[DesiredRelayState] = field(default_factory=list)
    subscription_page_enabled: bool = False


@dataclass
class ActualNodeState:
    """A node that currently exists in the panel."""

    host: str = ""
    name: str = ""
    uuid: str = ""
    is_connected: bool = False


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
            protocols=list(dn.protocols),
            domain=dn.domain,
            sni=dn.sni,
            warp=dn.warp,
        )
        for dn in cluster.desired_nodes
    ]

    relays = [
        DesiredRelayState(
            host=dr.host,
            name=dr.name,
            exit_node=dr.exit_node,
            ssh_user=dr.ssh_user,
            ssh_port=dr.ssh_port,
        )
        for dr in cluster.desired_relays
    ]

    sub_enabled = cluster.subscription_page.enabled if cluster.subscription_page else True

    return DesiredState(
        nodes=nodes,
        clients=list(cluster.desired_clients),
        relays=relays,
        subscription_page_enabled=sub_enabled,
    )


def build_actual_state(cluster: object, panel: object) -> ActualState:
    """Build ActualState from a ClusterConfig + panel API.

    Fetches live data from the panel to compare with desired state.
    """
    from meridian.cluster import ClusterConfig
    from meridian.remnawave import MeridianPanel

    if not isinstance(cluster, ClusterConfig) or not isinstance(panel, MeridianPanel):
        return ActualState()

    # Nodes: from cluster.yml (deployed topology) + panel API (connection status)
    actual_nodes = []
    api_nodes = {n.address: n for n in panel.list_nodes()}
    for node in cluster.nodes:
        api_node = api_nodes.get(node.ip)
        actual_nodes.append(
            ActualNodeState(
                host=node.ip,
                name=node.name,
                uuid=node.uuid,
                is_connected=api_node.is_connected if api_node else False,
            )
        )

    # Clients: from panel API
    actual_clients = [u.username for u in panel.list_users()]

    # Relays: from cluster.yml
    actual_relays = [
        ActualRelayState(
            host=r.ip,
            name=r.name,
            exit_node_ip=r.exit_node_ip,
        )
        for r in cluster.relays
    ]

    # Subscription page: check from cluster config
    sub_running = cluster.subscription_page.enabled if cluster.subscription_page else False

    return ActualState(
        nodes=actual_nodes,
        clients=actual_clients,
        relays=actual_relays,
        subscription_page_running=sub_running,
    )
