"""Tests for the reconciler — state, diff, executor, display.

The diff engine (compute_plan) is a pure function and gets the most
thorough testing. No mocking needed — just dataclass inputs and outputs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from meridian.reconciler.diff import Plan, PlanAction, PlanActionKind, compute_plan
from meridian.reconciler.display import print_plan
from meridian.reconciler.executor import ActionResult, ExecutionResult, execute_plan
from meridian.reconciler.state import (
    ActualNodeState,
    ActualRelayState,
    ActualState,
    DesiredNodeState,
    DesiredRelayState,
    DesiredState,
)

# ---------------------------------------------------------------------------
# compute_plan — pure diff tests
# ---------------------------------------------------------------------------


class TestComputePlanEmpty:
    def test_empty_desired_empty_actual(self) -> None:
        plan = compute_plan(DesiredState(), ActualState())
        assert plan.is_empty
        assert plan.summary() == "No changes. Infrastructure is up to date."

    def test_already_converged(self) -> None:
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1", name="node-1")],
            clients=["alice"],
        )
        actual = ActualState(
            nodes=[ActualNodeState(host="198.51.100.1", name="node-1")],
            clients=["alice"],
        )
        plan = compute_plan(desired, actual)
        assert plan.is_empty


class TestComputePlanNodes:
    def test_add_node(self) -> None:
        desired = DesiredState(nodes=[DesiredNodeState(host="198.51.100.1", name="node-1")])
        actual = ActualState()
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_NODE
        assert plan.actions[0].target == "198.51.100.1"
        assert not plan.actions[0].destructive

    def test_remove_node(self) -> None:
        desired = DesiredState()
        actual = ActualState(nodes=[ActualNodeState(host="198.51.100.1", name="node-1")])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_NODE
        assert plan.actions[0].destructive

    def test_add_and_remove_nodes(self) -> None:
        desired = DesiredState(nodes=[DesiredNodeState(host="198.51.100.2", name="new")])
        actual = ActualState(nodes=[ActualNodeState(host="198.51.100.1", name="old")])
        plan = compute_plan(desired, actual)
        kinds = {a.kind for a in plan.actions}
        assert PlanActionKind.ADD_NODE in kinds
        assert PlanActionKind.REMOVE_NODE in kinds

    def test_multiple_nodes_added(self) -> None:
        desired = DesiredState(
            nodes=[
                DesiredNodeState(host="198.51.100.1"),
                DesiredNodeState(host="198.51.100.2"),
                DesiredNodeState(host="198.51.100.3"),
            ]
        )
        actual = ActualState()
        plan = compute_plan(desired, actual)
        add_actions = [a for a in plan.actions if a.kind == PlanActionKind.ADD_NODE]
        assert len(add_actions) == 3


class TestComputePlanClients:
    def test_add_client(self) -> None:
        desired = DesiredState(clients=["alice", "bob"])
        actual = ActualState(clients=["alice"])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_CLIENT
        assert plan.actions[0].target == "bob"

    def test_remove_client(self) -> None:
        desired = DesiredState(clients=["alice"])
        actual = ActualState(clients=["alice", "bob"])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_CLIENT
        assert plan.actions[0].target == "bob"
        assert plan.actions[0].destructive

    def test_clients_sorted(self) -> None:
        desired = DesiredState(clients=["alice", "charlie", "eve"])
        actual = ActualState()
        plan = compute_plan(desired, actual)
        targets = [a.target for a in plan.actions if a.kind == PlanActionKind.ADD_CLIENT]
        assert targets == ["alice", "charlie", "eve"]


class TestComputePlanRelays:
    def test_add_relay(self) -> None:
        desired = DesiredState(relays=[DesiredRelayState(host="198.51.100.10", name="relay-1")])
        actual = ActualState()
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_RELAY

    def test_remove_relay(self) -> None:
        desired = DesiredState()
        actual = ActualState(relays=[ActualRelayState(host="198.51.100.10", name="relay-1")])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_RELAY
        assert plan.actions[0].destructive


class TestComputePlanSubscriptionPage:
    def test_add_subscription_page(self) -> None:
        desired = DesiredState(subscription_page_enabled=True)
        actual = ActualState(subscription_page_running=False)
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_SUBSCRIPTION_PAGE

    def test_remove_subscription_page(self) -> None:
        desired = DesiredState(subscription_page_enabled=False)
        actual = ActualState(subscription_page_running=True)
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_SUBSCRIPTION_PAGE
        assert plan.actions[0].destructive

    def test_subscription_page_already_running(self) -> None:
        desired = DesiredState(subscription_page_enabled=True)
        actual = ActualState(subscription_page_running=True)
        plan = compute_plan(desired, actual)
        sub_actions = [a for a in plan.actions if "subscription" in a.kind.value]
        assert len(sub_actions) == 0


class TestComputePlanComplex:
    def test_full_scenario(self) -> None:
        desired = DesiredState(
            nodes=[
                DesiredNodeState(host="198.51.100.1", name="kept"),
                DesiredNodeState(host="198.51.100.3", name="new"),
            ],
            clients=["alice", "charlie"],
            relays=[DesiredRelayState(host="198.51.100.10", name="relay-new")],
            subscription_page_enabled=True,
        )
        actual = ActualState(
            nodes=[
                ActualNodeState(host="198.51.100.1", name="kept"),
                ActualNodeState(host="198.51.100.2", name="removed"),
            ],
            clients=["alice", "bob"],
            relays=[ActualRelayState(host="198.51.100.20", name="relay-old")],
            subscription_page_running=False,
        )
        plan = compute_plan(desired, actual)

        kinds = [a.kind for a in plan.actions]
        assert PlanActionKind.ADD_NODE in kinds
        assert PlanActionKind.REMOVE_NODE in kinds
        assert PlanActionKind.ADD_CLIENT in kinds
        assert PlanActionKind.REMOVE_CLIENT in kinds
        assert PlanActionKind.ADD_RELAY in kinds
        assert PlanActionKind.REMOVE_RELAY in kinds
        assert PlanActionKind.ADD_SUBSCRIPTION_PAGE in kinds
        assert plan.has_destructive


# ---------------------------------------------------------------------------
# Plan properties
# ---------------------------------------------------------------------------


class TestPlanProperties:
    def test_symbol_add(self) -> None:
        action = PlanAction(kind=PlanActionKind.ADD_NODE, target="x")
        assert action.symbol == "+"

    def test_symbol_remove(self) -> None:
        action = PlanAction(kind=PlanActionKind.REMOVE_NODE, target="x")
        assert action.symbol == "-"

    def test_summary_with_adds_and_removes(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_NODE, target="a"),
                PlanAction(kind=PlanActionKind.ADD_CLIENT, target="b"),
                PlanAction(kind=PlanActionKind.REMOVE_CLIENT, target="c", destructive=True),
            ]
        )
        assert "2 to add" in plan.summary()
        assert "1 to remove" in plan.summary()

    def test_adds_and_removes_properties(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_NODE, target="a"),
                PlanAction(kind=PlanActionKind.REMOVE_NODE, target="b", destructive=True),
            ]
        )
        assert len(plan.adds) == 1
        assert len(plan.removes) == 1


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class TestExecutor:
    def test_executes_actions_with_callbacks(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_CLIENT, target="alice"),
                PlanAction(kind=PlanActionKind.ADD_CLIENT, target="bob"),
            ]
        )
        handler = MagicMock()
        result = execute_plan(plan, panel=None, cluster=None, callbacks={PlanActionKind.ADD_CLIENT: handler})
        assert result.all_succeeded
        assert handler.call_count == 2

    def test_handles_missing_callback(self) -> None:
        plan = Plan(actions=[PlanAction(kind=PlanActionKind.ADD_NODE, target="198.51.100.1")])
        result = execute_plan(plan, panel=None, cluster=None, callbacks={})
        assert not result.all_succeeded
        assert "no handler" in result.failed[0].error

    def test_handles_callback_error(self) -> None:
        plan = Plan(actions=[PlanAction(kind=PlanActionKind.ADD_CLIENT, target="alice")])
        handler = MagicMock(side_effect=RuntimeError("API down"))
        result = execute_plan(plan, panel=None, cluster=None, callbacks={PlanActionKind.ADD_CLIENT: handler})
        assert not result.all_succeeded
        assert "API down" in result.failed[0].error

    def test_continues_after_failure(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_CLIENT, target="alice"),
                PlanAction(kind=PlanActionKind.ADD_CLIENT, target="bob"),
            ]
        )
        call_count = 0

        def handler(action: PlanAction, panel: object, cluster: object) -> None:
            nonlocal call_count
            call_count += 1
            if action.target == "alice":
                raise RuntimeError("fail")

        result = execute_plan(plan, panel=None, cluster=None, callbacks={PlanActionKind.ADD_CLIENT: handler})
        assert call_count == 2
        assert len(result.failed) == 1
        assert result.results[1].success

    def test_execution_result_summary(self) -> None:
        result = ExecutionResult(
            results=[
                ActionResult(action=PlanAction(kind=PlanActionKind.ADD_CLIENT, target="a"), success=True),
                ActionResult(action=PlanAction(kind=PlanActionKind.ADD_CLIENT, target="b"), success=False, error="err"),
            ]
        )
        assert "1 succeeded" in result.summary()
        assert "1 failed" in result.summary()

    def test_empty_plan_succeeds(self) -> None:
        result = execute_plan(Plan(), panel=None, cluster=None)
        assert result.all_succeeded
        assert len(result.results) == 0


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


class TestDisplay:
    def test_print_empty_plan(self) -> None:
        console = MagicMock()
        print_plan(Plan(), console=console)
        call_args = [str(c) for c in console.print.call_args_list]
        assert any("No changes" in s for s in call_args)

    def test_print_plan_with_actions(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_NODE, target="198.51.100.1", detail="provision"),
                PlanAction(kind=PlanActionKind.REMOVE_CLIENT, target="bob", detail="delete", destructive=True),
            ]
        )
        console = MagicMock()
        print_plan(plan, console=console)
        assert console.print.call_count >= 3  # actions + summary + warning
