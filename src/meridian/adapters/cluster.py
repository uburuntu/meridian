"""ClusterConfig adapter for meridian-core topology models."""

from __future__ import annotations

from meridian.cluster import ClusterConfig
from meridian.core.fleet import (
    DesiredNodeSpec,
    DesiredRelaySpec,
    FleetTopology,
    RelayHostRef,
    TopologyNode,
    TopologyPanel,
    TopologyRelay,
    TopologySubscriptionPage,
)


def topology_from_cluster(cluster: ClusterConfig) -> FleetTopology:
    """Convert the current YAML-backed cluster model into core topology."""
    return FleetTopology(
        panel=TopologyPanel(
            url=cluster.panel.url,
            display_url=cluster.panel.display_url,
            server_ip=cluster.panel.server_ip,
            ssh_user=cluster.panel.ssh_user,
            ssh_port=cluster.panel.ssh_port,
            deployed_with=cluster.panel.deployed_with,
        ),
        subscription_page=(
            TopologySubscriptionPage(
                enabled=cluster.subscription_page.enabled,
                path=cluster.subscription_page.path,
            )
            if cluster.subscription_page
            else None
        ),
        nodes=[
            TopologyNode(
                ip=node.ip,
                name=node.name,
                uuid=node.uuid,
                is_panel_host=node.is_panel_host,
                ssh_user=node.ssh_user,
                ssh_port=node.ssh_port,
                domain=node.domain,
                sni=node.sni,
                xhttp_path=node.xhttp_path,
                ws_path=node.ws_path,
            )
            for node in cluster.nodes
        ],
        relays=[
            TopologyRelay(
                ip=relay.ip,
                name=relay.name,
                port=relay.port,
                ssh_user=relay.ssh_user,
                ssh_port=relay.ssh_port,
                exit_node_ip=relay.exit_node_ip,
                sni=relay.sni,
                host_refs=[
                    RelayHostRef(protocol=str(protocol), uuid=uuid)
                    for protocol, uuid in sorted(relay.host_uuids.items())
                ],
            )
            for relay in cluster.relays
        ],
        desired_nodes=(
            [
                DesiredNodeSpec(
                    host=desired.host,
                    name=desired.name,
                    ssh_user=desired.ssh_user,
                    ssh_port=desired.ssh_port,
                    domain=desired.domain,
                    sni=desired.sni,
                    warp=desired.warp,
                )
                for desired in cluster.desired_nodes
            ]
            if cluster.desired_nodes is not None
            else None
        ),
        desired_relays=(
            [
                DesiredRelaySpec(
                    host=desired.host,
                    name=desired.name,
                    ssh_user=desired.ssh_user,
                    ssh_port=desired.ssh_port,
                    exit_node=desired.exit_node,
                    sni=desired.sni,
                )
                for desired in cluster.desired_relays
            ]
            if cluster.desired_relays is not None
            else None
        ),
    )
