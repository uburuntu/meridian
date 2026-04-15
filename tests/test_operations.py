"""Tests for operations.py — reusable provisioning operations.

Uses MagicMock for panel API and cluster config mutations.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from meridian.cluster import ClusterConfig, NodeEntry, PanelConfig, RelayEntry
from meridian.operations import add_client, remove_client, remove_node, update_node
from meridian.remnawave import MeridianPanel


def _make_cluster(**kwargs) -> ClusterConfig:
    defaults = {
        "version": 2,
        "panel": PanelConfig(url="https://198.51.100.1/panel", api_token="tok", server_ip="198.51.100.1"),
    }
    defaults.update(kwargs)
    return ClusterConfig(**defaults)


def _mock_panel() -> MagicMock:
    panel = MagicMock(spec=MeridianPanel)
    return panel


# ---------------------------------------------------------------------------
# Client operations
# ---------------------------------------------------------------------------


class TestAddClient:
    def test_passes_squad_uuids(self) -> None:
        cluster = _make_cluster(squad_uuid="sq-1")
        panel = _mock_panel()
        panel.create_user.return_value = SimpleNamespace(uuid="u-1", username="alice")
        add_client(cluster, panel, name="alice")
        panel.create_user.assert_called_once_with("alice", squad_uuids=["sq-1"])

    def test_no_squad_when_empty(self) -> None:
        cluster = _make_cluster(squad_uuid="")
        panel = _mock_panel()
        panel.create_user.return_value = SimpleNamespace(uuid="u-1", username="alice")
        add_client(cluster, panel, name="alice")
        panel.create_user.assert_called_once_with("alice", squad_uuids=None)


class TestRemoveClient:
    def test_looks_up_by_username_then_deletes(self) -> None:
        cluster = _make_cluster()
        panel = _mock_panel()
        panel.get_user.return_value = SimpleNamespace(uuid="u-1", username="alice")
        panel.delete_user.return_value = True
        result = remove_client(cluster, panel, name="alice")
        panel.get_user.assert_called_once_with("alice")
        panel.delete_user.assert_called_once_with("u-1")
        assert result is True

    def test_returns_false_when_user_not_found(self) -> None:
        cluster = _make_cluster()
        panel = _mock_panel()
        panel.get_user.return_value = None
        result = remove_client(cluster, panel, name="ghost")
        assert result is False


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------


class TestRemoveNode:
    def test_removes_cluster_tracked_node(self) -> None:
        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2", name="node-2")
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()
        remove_node(cluster, panel, node_ip="198.51.100.2")
        panel.disable_node.assert_called_once_with("uuid-2")
        panel.delete_node.assert_called_once_with("uuid-2")
        assert len(cluster.nodes) == 0

    def test_rejects_panel_host(self) -> None:
        node = NodeEntry(ip="198.51.100.1", uuid="uuid-1", is_panel_host=True)
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()
        with pytest.raises(ValueError, match="panel node"):
            remove_node(cluster, panel, node_ip="198.51.100.1")

    def test_rejects_node_with_dependent_relays(self) -> None:
        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2")
        relay = RelayEntry(ip="198.51.100.10", exit_node_ip="198.51.100.2")
        cluster = _make_cluster(nodes=[node], relays=[relay])
        panel = _mock_panel()
        with pytest.raises(ValueError, match="relays depend"):
            remove_node(cluster, panel, node_ip="198.51.100.2")

    def test_panel_only_node_lookup_by_address(self) -> None:
        """Node not in cluster.yml but exists in panel API."""
        cluster = _make_cluster(nodes=[])
        panel = _mock_panel()
        panel.find_node_by_address.return_value = SimpleNamespace(uuid="api-uuid")
        remove_node(cluster, panel, node_ip="198.51.100.5")
        panel.find_node_by_address.assert_called_once_with("198.51.100.5")
        panel.disable_node.assert_called_once_with("api-uuid")
        panel.delete_node.assert_called_once_with("api-uuid")


class TestUpdateNode:
    def test_rollback_on_failed_redeploy(self) -> None:
        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2", name="old", sni="old.sni", domain="old.dom", warp=False)
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()

        with (
            patch("meridian.commands.setup._setup_redeploy", side_effect=RuntimeError("SSH failed")),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.resolve.ResolvedServer"),
        ):
            with pytest.raises(RuntimeError, match="SSH failed"):
                update_node(cluster, panel, ip="198.51.100.2", name="new", sni="new.sni")

        # Metadata should be rolled back
        assert node.name == "old"
        assert node.sni == "old.sni"

    def test_name_update_calls_panel_api(self) -> None:
        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2", name="old-name")
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()

        with (
            patch("meridian.commands.setup._setup_redeploy"),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.resolve.ResolvedServer"),
        ):
            update_node(cluster, panel, ip="198.51.100.2", name="new-name")

        assert node.name == "new-name"
        panel.update_node_name.assert_called_once_with("uuid-2", "new-name")


# ---------------------------------------------------------------------------
# Error/failure paths surfaced by the Codex test-quality review
# ---------------------------------------------------------------------------


class TestRemoveNodeErrorPaths:
    """Codex review: panel-side failures during remove_node should not leave
    cluster.yml in an inconsistent state, and remove_node should still finish
    its local cleanup so a retry can proceed.
    """

    def test_panel_disable_failure_does_not_block_local_remove(self) -> None:
        from meridian.remnawave import RemnawaveError

        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2", name="x")
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()
        panel.disable_node.side_effect = RemnawaveError("panel down")
        # delete_node still attempted — also failing here exercises the warn path
        panel.delete_node.side_effect = RemnawaveError("panel down")

        # remove_node must NOT raise — it logs and proceeds with local cleanup
        # so the operator can retry without manual cluster.yml surgery.
        remove_node(cluster, panel, node_ip="198.51.100.2")
        assert cluster.nodes == []

    def test_force_overrides_dependent_relay_check(self) -> None:
        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2")
        relay = RelayEntry(ip="198.51.100.10", exit_node_ip="198.51.100.2")
        cluster = _make_cluster(nodes=[node], relays=[relay])
        panel = _mock_panel()
        # Without force, the dependent-relays check refuses the remove.
        # With force=True, the operator accepts the orphan and we proceed.
        remove_node(cluster, panel, node_ip="198.51.100.2", force=True)
        assert cluster.nodes == []
        # Relay is intentionally not auto-removed — operator can clean separately
        assert len(cluster.relays) == 1


class TestUpdateNodeMetadataConsistency:
    """update_node mutates the node metadata BEFORE the redeploy runs so that
    _setup_redeploy reads the new SNI/name. If redeploy fails, the rollback
    must restore EVERY field that was tentatively changed — otherwise
    cluster.yml claims state that the server never reached.
    """

    def test_rollback_restores_all_changed_fields(self) -> None:
        node = NodeEntry(
            ip="198.51.100.2",
            uuid="uuid-2",
            name="old-name",
            sni="old.sni",
            domain="old.dom",
            warp=False,
        )
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()

        with (
            patch("meridian.commands.setup._setup_redeploy", side_effect=RuntimeError("provisioner died")),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.resolve.ResolvedServer"),
        ):
            with pytest.raises(RuntimeError):
                update_node(
                    cluster,
                    panel,
                    ip="198.51.100.2",
                    name="new-name",
                    sni="new.sni",
                    domain="new.dom",
                    warp=True,
                )

        # Every changed field must be the original value.
        assert node.name == "old-name"
        assert node.sni == "old.sni"
        assert node.domain == "old.dom"
        assert node.warp is False
        # Panel update should NOT have been called when redeploy never finished.
        panel.update_node_name.assert_not_called()

    def test_panel_name_update_failure_does_not_undo_local_change(self) -> None:
        from meridian.remnawave import RemnawaveError

        node = NodeEntry(ip="198.51.100.2", uuid="uuid-2", name="old-name")
        cluster = _make_cluster(nodes=[node])
        panel = _mock_panel()
        panel.update_node_name.side_effect = RemnawaveError("panel down")

        with (
            patch("meridian.commands.setup._setup_redeploy"),  # provisioner OK
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.resolve.ResolvedServer"),
        ):
            update_node(cluster, panel, ip="198.51.100.2", name="new-name")

        # The redeploy succeeded so the local rename should stick even if the
        # panel name sync fails — the panel name is cosmetic and we recover
        # next apply.
        assert node.name == "new-name"


class TestAddClientErrorPaths:
    def test_panel_create_failure_propagates(self) -> None:
        from meridian.remnawave import RemnawaveError

        cluster = _make_cluster(squad_uuid="sq-1")
        panel = _mock_panel()
        panel.create_user.side_effect = RemnawaveError("user already exists")

        with pytest.raises(RemnawaveError, match="already exists"):
            add_client(cluster, panel, name="alice")
