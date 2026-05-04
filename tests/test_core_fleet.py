"""Tests for meridian-core fleet inventory model."""

from __future__ import annotations

from dataclasses import dataclass

from meridian.cluster import ClusterConfig, DesiredNode, DesiredRelay, NodeEntry, PanelConfig, RelayEntry
from meridian.core.fleet import build_fleet_inventory


@dataclass
class ApiNode:
    uuid: str
    is_connected: bool = True
    is_disabled: bool = False
    xray_version: str = "25.12.1"


def test_inventory_is_redacted_and_role_protocol_aware() -> None:
    cluster = ClusterConfig(
        panel=PanelConfig(url="https://198.51.100.1/panel", api_token="secret-token", server_ip="198.51.100.1"),
        nodes=[
            NodeEntry(
                ip="198.51.100.1",
                uuid="node-a",
                name="exit-a",
                is_panel_host=True,
                xhttp_path="xhttp-a",
            )
        ],
        relays=[RelayEntry(ip="198.51.100.2", name="relay-a", exit_node_ip="198.51.100.1")],
        desired_nodes=[DesiredNode(host="198.51.100.1", name="exit-a")],
        desired_relays=[DesiredRelay(host="198.51.100.2", name="relay-a", exit_node="exit-a")],
    )

    inventory = build_fleet_inventory(cluster, panel_healthy=True, api_nodes=[ApiNode(uuid="node-a")])
    data = inventory.to_data()

    assert "api_token" not in data["panel"]
    assert data["panel"]["healthy"] is True
    assert data["nodes"][0]["protocols"] == ["reality", "xhttp"]
    assert data["nodes"][0]["panel_status"] == "connected"
    assert data["relays"][0]["exit_node_name"] == "exit-a"
    assert data["summary"]["unapplied_desired_nodes"] == 0
    assert data["summary"]["unapplied_desired_relays"] == 0


def test_inventory_desired_matching_uses_host_identity() -> None:
    cluster = ClusterConfig(
        panel=PanelConfig(url="https://198.51.100.1/panel", api_token="secret-token"),
        nodes=[NodeEntry(ip="198.51.100.1", uuid="node-a", name="reused-name")],
        relays=[RelayEntry(ip="198.51.100.2", name="reused-relay")],
        desired_nodes=[DesiredNode(host="198.51.100.9", name="reused-name")],
        desired_relays=[DesiredRelay(host="198.51.100.8", name="reused-relay", exit_node="reused-name")],
    )

    inventory = build_fleet_inventory(cluster, panel_healthy=False)
    data = inventory.to_data()

    assert data["nodes"][0]["desired"] is False
    assert data["relays"][0]["desired"] is False
    assert data["desired_nodes"][0]["present"] is False
    assert data["desired_relays"][0]["present"] is False
    assert data["summary"]["unapplied_desired_nodes"] == 1
    assert data["summary"]["unapplied_desired_relays"] == 1
