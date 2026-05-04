"""Fleet inventory data model and builders for meridian-core."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from pydantic import Field

from meridian.cluster import ClusterConfig, DesiredNode, DesiredRelay, NodeEntry, RelayEntry
from meridian.core.models import CoreModel


class ApiNodeLike(Protocol):
    uuid: str


class PanelInventory(CoreModel):
    url: str
    server_ip: str
    ssh_user: str
    ssh_port: int
    healthy: bool
    deployed_with: str
    subscription_page: dict[str, Any]


class NodeInventory(CoreModel):
    ip: str
    name: str
    uuid: str
    role: str
    ssh_user: str
    ssh_port: int
    domain: str
    sni: str
    protocols: list[str]
    desired: bool | None
    panel_status: str
    xray_version: str


class RelayInventory(CoreModel):
    ip: str
    name: str
    role: str
    port: int
    ssh_user: str
    ssh_port: int
    exit_node_ip: str
    exit_node_name: str
    sni: str
    host_count: int
    desired: bool | None


class DesiredNodeInventory(CoreModel):
    host: str
    name: str
    ssh_user: str
    ssh_port: int
    domain: str
    sni: str
    warp: bool | None
    present: bool


class DesiredRelayInventory(CoreModel):
    host: str
    name: str
    ssh_user: str
    ssh_port: int
    exit_node: str
    sni: str
    present: bool


class FleetInventorySummary(CoreModel):
    nodes: int
    relays: int
    desired_nodes: int
    desired_relays: int
    unapplied_desired_nodes: int
    unapplied_desired_relays: int

    @property
    def pending(self) -> int:
        return self.unapplied_desired_nodes + self.unapplied_desired_relays

    @property
    def text(self) -> str:
        return f"{self.nodes} node(s), {self.relays} relay(s), {self.pending} pending desired resource(s)"


class FleetInventory(CoreModel):
    panel: PanelInventory
    summary: FleetInventorySummary
    nodes: list[NodeInventory] = Field(default_factory=list)
    relays: list[RelayInventory] = Field(default_factory=list)
    desired_nodes: list[DesiredNodeInventory] = Field(default_factory=list)
    desired_relays: list[DesiredRelayInventory] = Field(default_factory=list)

    def to_data(self) -> dict[str, Any]:
        from meridian.core.serde import to_plain

        return to_plain(self)


def node_api_status(api_node: ApiNodeLike | None) -> str:
    if not api_node:
        return "unknown"
    if getattr(api_node, "is_connected", False):
        return "connected"
    if getattr(api_node, "is_disabled", False):
        return "disabled"
    return "disconnected"


def node_protocols(node: NodeEntry) -> list[str]:
    protocols = ["reality"]
    if node.xhttp_path:
        protocols.append("xhttp")
    if node.domain and node.ws_path:
        protocols.append("wss")
    return protocols


def node_desired(node: NodeEntry, desired_nodes: list[DesiredNode] | None) -> bool | None:
    if desired_nodes is None:
        return None
    return any(node.ip == desired.host for desired in desired_nodes)


def relay_desired(relay: RelayEntry, desired_relays: list[DesiredRelay] | None) -> bool | None:
    if desired_relays is None:
        return None
    return any(relay.ip == desired.host for desired in desired_relays)


def build_fleet_inventory(
    cluster: ClusterConfig,
    *,
    panel_healthy: bool,
    api_nodes: Sequence[ApiNodeLike] | None = None,
) -> FleetInventory:
    """Build a redacted fleet inventory from local state plus panel status."""
    api_by_uuid = {node.uuid: node for node in api_nodes or []}
    desired_node_hosts = {d.host for d in cluster.desired_nodes or [] if d.host}
    desired_relay_hosts = {d.host for d in cluster.desired_relays or [] if d.host}
    actual_node_hosts = {node.ip for node in cluster.nodes if node.ip}
    actual_relay_hosts = {relay.ip for relay in cluster.relays if relay.ip}

    panel = PanelInventory(
        url=cluster.panel.display_url or cluster.panel.url,
        server_ip=cluster.panel.server_ip,
        ssh_user=cluster.panel.ssh_user,
        ssh_port=cluster.panel.ssh_port,
        healthy=panel_healthy,
        deployed_with=cluster.panel.deployed_with,
        subscription_page={
            "enabled": bool(cluster.subscription_page and cluster.subscription_page.enabled),
            "path": cluster.subscription_page.path if cluster.subscription_page else "",
        },
    )

    nodes = []
    for node in cluster.nodes:
        api_node = api_by_uuid.get(node.uuid)
        nodes.append(
            NodeInventory(
                ip=node.ip,
                name=node.name,
                uuid=node.uuid,
                role="panel+node" if node.is_panel_host else "node",
                ssh_user=node.ssh_user,
                ssh_port=node.ssh_port,
                domain=node.domain,
                sni=node.sni,
                protocols=node_protocols(node),
                desired=node_desired(node, cluster.desired_nodes),
                panel_status=node_api_status(api_node),
                xray_version=getattr(api_node, "xray_version", "") if api_node else "",
            )
        )

    relays = []
    for relay in cluster.relays:
        exit_node = cluster.find_node(relay.exit_node_ip)
        relays.append(
            RelayInventory(
                ip=relay.ip,
                name=relay.name,
                role="relay",
                port=relay.port,
                ssh_user=relay.ssh_user,
                ssh_port=relay.ssh_port,
                exit_node_ip=relay.exit_node_ip,
                exit_node_name=exit_node.name if exit_node else "",
                sni=relay.sni,
                host_count=len(relay.host_uuids),
                desired=relay_desired(relay, cluster.desired_relays),
            )
        )

    desired_nodes = [
        DesiredNodeInventory(
            host=desired.host,
            name=desired.name,
            ssh_user=desired.ssh_user,
            ssh_port=desired.ssh_port,
            domain=desired.domain,
            sni=desired.sni,
            warp=desired.warp,
            present=bool(desired.host and desired.host in actual_node_hosts),
        )
        for desired in cluster.desired_nodes or []
    ]
    desired_relays = [
        DesiredRelayInventory(
            host=desired.host,
            name=desired.name,
            ssh_user=desired.ssh_user,
            ssh_port=desired.ssh_port,
            exit_node=desired.exit_node,
            sni=desired.sni,
            present=bool(desired.host and desired.host in actual_relay_hosts),
        )
        for desired in cluster.desired_relays or []
    ]

    summary = FleetInventorySummary(
        nodes=len(cluster.nodes),
        relays=len(cluster.relays),
        desired_nodes=len(cluster.desired_nodes or []),
        desired_relays=len(cluster.desired_relays or []),
        unapplied_desired_nodes=len(desired_node_hosts - actual_node_hosts),
        unapplied_desired_relays=len(desired_relay_hosts - actual_relay_hosts),
    )
    return FleetInventory(
        panel=panel,
        summary=summary,
        nodes=nodes,
        relays=relays,
        desired_nodes=desired_nodes,
        desired_relays=desired_relays,
    )
