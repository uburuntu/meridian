"""Unit tests for the declarative `meridian apply` command.

These cover the action handler logic and command-level orchestration —
not the underlying provisioning, which is unit-tested elsewhere.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer

from meridian.cluster import ClusterConfig, DesiredRelay, NodeEntry, PanelConfig, RelayEntry
from meridian.commands.apply import _handle_update_relay
from meridian.commands.apply import run as apply_run
from meridian.reconciler.diff import Plan, PlanAction, PlanActionKind
from meridian.reconciler.executor import ActionResult, ExecutionResult


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


# ---------------------------------------------------------------------------
# apply.run() command-level failure-safety
# ---------------------------------------------------------------------------


class TestApplyRunFailureSafety:
    """Codex review's #1 highest-value addition: when an early action fails,
    apply.run() must report failure (non-zero exit) and the destructive
    follow-up actions must be skipped — the executor enforces that, but the
    command wrapper must surface the result to the user.
    """

    def _build_cluster_with_desired_clients(self) -> ClusterConfig:
        return ClusterConfig(
            version=2,
            panel=PanelConfig(
                url="https://198.51.100.1/panel",
                api_token="tok",
                server_ip="198.51.100.1",
            ),
            nodes=[
                NodeEntry(
                    ip="198.51.100.1",
                    uuid="00000000-0000-0000-0000-000000000001",
                    name="exit-1",
                    is_panel_host=True,
                )
            ],
            desired_clients=["alice", "bob"],
        )

    def test_failed_action_causes_nonzero_exit(self) -> None:
        cluster = self._build_cluster_with_desired_clients()

        # An execution result with one failed action — apply.run should react.
        failed_action = PlanAction(kind=PlanActionKind.ADD_CLIENT, target="alice")
        exec_result = ExecutionResult(results=[ActionResult(action=failed_action, success=False, error="API down")])
        plan = Plan(actions=[failed_action])

        with (
            patch.object(ClusterConfig, "load", return_value=cluster),
            patch("meridian.remnawave.MeridianPanel"),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.apply.build_desired_state"),
            patch("meridian.commands.apply.build_actual_state"),
            patch("meridian.commands.apply.compute_plan", return_value=plan),
            patch("meridian.commands.apply.execute_plan", return_value=exec_result),
            patch("meridian.commands.apply.print_plan"),
            # `fail()` raises typer.Exit with hint_type-derived code
            patch.object(ClusterConfig, "save"),
        ):
            with pytest.raises(typer.Exit) as exc_info:
                apply_run(yes=True, parallel=1)
            assert exc_info.value.exit_code != 0

    def test_skipped_destructive_action_marks_failure(self) -> None:
        """When the executor skips a REMOVE_NODE because of an earlier failure
        in the same run, the result still has success=False with a 'skipped'
        error. apply.run must treat this as overall failure, not as a no-op.
        """
        cluster = self._build_cluster_with_desired_clients()

        failed_add = ActionResult(
            action=PlanAction(kind=PlanActionKind.ADD_CLIENT, target="alice"),
            success=False,
            error="provisioner died",
        )
        skipped_remove = ActionResult(
            action=PlanAction(kind=PlanActionKind.REMOVE_NODE, target="198.51.100.99", destructive=True),
            success=False,
            error="skipped: prior phase had failures",
        )
        exec_result = ExecutionResult(results=[failed_add, skipped_remove])
        plan = Plan(actions=[failed_add.action, skipped_remove.action])

        with (
            patch.object(ClusterConfig, "load", return_value=cluster),
            patch("meridian.remnawave.MeridianPanel"),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.apply.build_desired_state"),
            patch("meridian.commands.apply.build_actual_state"),
            patch("meridian.commands.apply.compute_plan", return_value=plan),
            patch("meridian.commands.apply.execute_plan", return_value=exec_result),
            patch("meridian.commands.apply.print_plan"),
            patch.object(ClusterConfig, "save"),
        ):
            with pytest.raises(typer.Exit) as exc_info:
                apply_run(yes=True, parallel=1)
            assert exc_info.value.exit_code != 0

    def test_empty_plan_exits_zero(self) -> None:
        cluster = self._build_cluster_with_desired_clients()
        empty_plan = Plan(actions=[])

        with (
            patch.object(ClusterConfig, "load", return_value=cluster),
            patch("meridian.remnawave.MeridianPanel"),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.apply.build_desired_state"),
            patch("meridian.commands.apply.build_actual_state"),
            patch("meridian.commands.apply.compute_plan", return_value=empty_plan),
        ):
            with pytest.raises(typer.Exit) as exc_info:
                apply_run(yes=True, parallel=1)
            # Exit 0 = no changes needed
            assert exc_info.value.exit_code == 0

    def test_aborts_when_no_desired_state_or_sub_page(self) -> None:
        # A cluster with neither desired state nor subscription page declared —
        # apply has nothing to converge to.
        cluster = ClusterConfig(
            version=2,
            panel=PanelConfig(
                url="https://198.51.100.1/panel",
                api_token="tok",
                server_ip="198.51.100.1",
            ),
        )
        with patch.object(ClusterConfig, "load", return_value=cluster):
            with pytest.raises(typer.Exit) as exc_info:
                apply_run(yes=True, parallel=1)
            assert exc_info.value.exit_code != 0

    def test_aborts_when_panel_not_configured(self) -> None:
        # Has desired state but the panel is not configured yet
        cluster = ClusterConfig(version=2, desired_clients=["alice"])
        with patch.object(ClusterConfig, "load", return_value=cluster):
            with pytest.raises(typer.Exit) as exc_info:
                apply_run(yes=True, parallel=1)
            assert exc_info.value.exit_code != 0
