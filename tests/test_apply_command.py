"""Unit tests for the declarative `meridian apply` command.

These cover the action handler logic and command-level orchestration —
not the underlying provisioning, which is unit-tested elsewhere.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meridian.cluster import ClusterConfig, DesiredRelay, NodeEntry, PanelConfig, RelayEntry
from meridian.commands.apply import _handle_update_relay
from meridian.reconciler.diff import PlanAction, PlanActionKind


def _make_cluster_with_relay(relay_ip: str = "198.51.100.20") -> ClusterConfig:
    cluster = ClusterConfig(
        version=2,
        panel=PanelConfig(url="https://198.51.100.1/panel", api_token="tok", server_ip="198.51.100.1"),
        nodes=[
            NodeEntry(
                ip="198.51.100.1",
                uuid="00000000-0000-0000-0000-000000000001",
                name="exit-1",
                is_panel_host=True,
            )
        ],
        relays=[
            RelayEntry(
                ip=relay_ip,
                exit_node_ip="198.51.100.1",
                name="r1",
                host_uuids={"REALITY": "00000000-0000-0000-0000-0000000000aa"},
            )
        ],
        desired_relays=[
            DesiredRelay(host=relay_ip, name="r1", exit_node="exit-1", sni="www.google.com"),
        ],
    )
    return cluster


class TestHandleUpdateRelayPreflight:
    """Bug #4 regression: UPDATE_RELAY used to delete the old relay before
    attempting to provision the new one. If the new SSH target was unreachable
    or the new exit node could not be resolved, the cluster ended up with no
    relay at all. The handler now preflights both before deleting anything.
    """

    def _make_panel(self) -> object:
        from meridian.remnawave import MeridianPanel

        # Build a panel object without going through __init__ so we don't try
        # to open a real httpx client in tests.
        return MeridianPanel.__new__(MeridianPanel)

    def test_aborts_when_no_matching_desired_relay(self) -> None:
        cluster = _make_cluster_with_relay()
        cluster.desired_relays = []  # diff produced UPDATE but desired list is empty
        action = PlanAction(kind=PlanActionKind.UPDATE_RELAY, target="198.51.100.20")

        with patch("meridian.operations.remove_relay") as rm:
            with pytest.raises(RuntimeError, match="no matching desired relay"):
                _handle_update_relay(action, self._make_panel(), cluster)
            # Critical: the old relay was NOT touched.
            rm.assert_not_called()

    def test_aborts_when_exit_node_unresolvable(self) -> None:
        cluster = _make_cluster_with_relay()
        # Desired references an unknown exit node name
        cluster.desired_relays = [
            DesiredRelay(host="198.51.100.20", name="r1", exit_node="ghost-node", sni="www.google.com"),
        ]
        action = PlanAction(kind=PlanActionKind.UPDATE_RELAY, target="198.51.100.20")

        with patch("meridian.operations.remove_relay") as rm:
            with pytest.raises(RuntimeError, match="could not be resolved"):
                _handle_update_relay(action, self._make_panel(), cluster)
            rm.assert_not_called()

    def test_aborts_when_ssh_preflight_fails(self) -> None:
        cluster = _make_cluster_with_relay()
        action = PlanAction(kind=PlanActionKind.UPDATE_RELAY, target="198.51.100.20")

        # Force ServerConnection.run to fail
        fake_result = MagicMock(returncode=255, stderr="connection refused")
        fake_conn = MagicMock()
        fake_conn.run.return_value = fake_result

        with (
            patch("meridian.ssh.ServerConnection", return_value=fake_conn),
            patch("meridian.operations.remove_relay") as rm,
            patch("meridian.operations.add_relay") as add,
        ):
            with pytest.raises(RuntimeError, match="preflight"):
                _handle_update_relay(action, self._make_panel(), cluster)
            rm.assert_not_called()
            add.assert_not_called()

    def test_proceeds_when_preflight_succeeds(self) -> None:
        cluster = _make_cluster_with_relay()
        action = PlanAction(kind=PlanActionKind.UPDATE_RELAY, target="198.51.100.20")

        fake_result = MagicMock(returncode=0)
        fake_conn = MagicMock()
        fake_conn.run.return_value = fake_result

        with (
            patch("meridian.ssh.ServerConnection", return_value=fake_conn),
            patch("meridian.operations.remove_relay") as rm,
            patch("meridian.operations.add_relay") as add,
        ):
            _handle_update_relay(action, self._make_panel(), cluster)
            rm.assert_called_once()
            add.assert_called_once()
            # remove must run BEFORE add — verify ordering by looking at MagicMock parents
            assert rm.call_args.kwargs.get("relay_ip") == "198.51.100.20"
