"""Tests for the reconciler — state, diff, executor, display, state builders.

The diff engine (compute_plan) is a pure function and gets the most
thorough testing. No mocking needed — just dataclass inputs and outputs.
State builder tests use mocked panel API and cluster config.
"""

from __future__ import annotations

from types import SimpleNamespace
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
    build_actual_state,
    build_desired_state,
)

# ---------------------------------------------------------------------------
# compute_plan — pure diff tests
# ---------------------------------------------------------------------------


class TestComputePlanEmpty:
    def test_empty_desired_empty_actual(self) -> None:
        plan = compute_plan(DesiredState(), ActualState())
        assert plan.is_empty

    def test_already_converged(self) -> None:
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1", name="node-1")],
            clients=["alice"],
            manage_nodes=True,
            manage_clients=True,
        )
        actual = ActualState(
            nodes=[ActualNodeState(host="198.51.100.1", name="node-1")],
            clients=["alice"],
        )
        plan = compute_plan(desired, actual)
        assert plan.is_empty


class TestComputePlanNodes:
    def test_add_node(self) -> None:
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1", name="node-1")],
            manage_nodes=True,
        )
        actual = ActualState()
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_NODE
        assert plan.actions[0].target == "198.51.100.1"

    def test_remove_node(self) -> None:
        desired = DesiredState(manage_nodes=True)
        actual = ActualState(nodes=[ActualNodeState(host="198.51.100.1", name="node-1")])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_NODE
        assert plan.actions[0].destructive

    def test_update_node_sni_changed(self) -> None:
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1", sni="www.apple.com")],
            manage_nodes=True,
        )
        actual = ActualState(
            nodes=[ActualNodeState(host="198.51.100.1", sni="www.microsoft.com")],
        )
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.UPDATE_NODE
        assert "sni" in plan.actions[0].detail

    def test_update_node_warp_changed(self) -> None:
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1", warp=True)],
            manage_nodes=True,
        )
        actual = ActualState(
            nodes=[ActualNodeState(host="198.51.100.1", warp=False)],
        )
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.UPDATE_NODE

    def test_no_update_when_attributes_match(self) -> None:
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1", sni="www.microsoft.com", warp=False)],
            manage_nodes=True,
        )
        actual = ActualState(
            nodes=[ActualNodeState(host="198.51.100.1", sni="www.microsoft.com", warp=False)],
        )
        plan = compute_plan(desired, actual)
        assert plan.is_empty

    def test_multiple_nodes_added(self) -> None:
        desired = DesiredState(
            nodes=[
                DesiredNodeState(host="198.51.100.1"),
                DesiredNodeState(host="198.51.100.2"),
                DesiredNodeState(host="198.51.100.3"),
            ],
            manage_nodes=True,
        )
        actual = ActualState()
        plan = compute_plan(desired, actual)
        add_actions = [a for a in plan.actions if a.kind == PlanActionKind.ADD_NODE]
        assert len(add_actions) == 3


class TestComputePlanClients:
    def test_add_client(self) -> None:
        desired = DesiredState(clients=["alice", "bob"], manage_clients=True)
        actual = ActualState(clients=["alice"])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_CLIENT
        assert plan.actions[0].target == "bob"

    def test_remove_client(self) -> None:
        desired = DesiredState(clients=["alice"], manage_clients=True)
        actual = ActualState(clients=["alice", "bob"])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_CLIENT
        assert plan.actions[0].destructive

    def test_clients_sorted(self) -> None:
        desired = DesiredState(clients=["alice", "charlie", "eve"], manage_clients=True)
        actual = ActualState()
        plan = compute_plan(desired, actual)
        targets = [a.target for a in plan.actions if a.kind == PlanActionKind.ADD_CLIENT]
        assert targets == ["alice", "charlie", "eve"]


class TestComputePlanRelays:
    def test_add_relay(self) -> None:
        desired = DesiredState(
            relays=[DesiredRelayState(host="198.51.100.10", name="relay-1")],
            manage_relays=True,
        )
        actual = ActualState()
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_RELAY

    def test_remove_relay(self) -> None:
        desired = DesiredState(manage_relays=True)
        actual = ActualState(relays=[ActualRelayState(host="198.51.100.10", name="relay-1")])
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_RELAY
        assert plan.actions[0].destructive

    def test_update_relay_exit_changed(self) -> None:
        desired = DesiredState(
            relays=[DesiredRelayState(host="198.51.100.10", exit_node="198.51.100.2")],
            manage_relays=True,
        )
        actual = ActualState(
            relays=[ActualRelayState(host="198.51.100.10", exit_node_ip="198.51.100.1")],
        )
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.UPDATE_RELAY


class TestComputePlanSubscriptionPage:
    def test_add_subscription_page(self) -> None:
        desired = DesiredState(subscription_page_enabled=True, manage_subscription_page=True)
        actual = ActualState(subscription_page_running=False)
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.ADD_SUBSCRIPTION_PAGE

    def test_remove_subscription_page(self) -> None:
        desired = DesiredState(subscription_page_enabled=False, manage_subscription_page=True)
        actual = ActualState(subscription_page_running=True)
        plan = compute_plan(desired, actual)
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == PlanActionKind.REMOVE_SUBSCRIPTION_PAGE
        assert plan.actions[0].destructive

    def test_subscription_page_already_running(self) -> None:
        desired = DesiredState(subscription_page_enabled=True, manage_subscription_page=True)
        actual = ActualState(subscription_page_running=True)
        plan = compute_plan(desired, actual)
        sub_actions = [a for a in plan.actions if "subscription" in a.kind.value]
        assert len(sub_actions) == 0

    def test_unmanaged_subscription_page_not_touched(self) -> None:
        """Legacy cluster without subscription_page section — no actions."""
        desired = DesiredState(manage_subscription_page=False)
        actual = ActualState(subscription_page_running=True)
        plan = compute_plan(desired, actual)
        sub_actions = [a for a in plan.actions if "subscription" in a.kind.value]
        assert len(sub_actions) == 0


class TestComputePlanPartialConfig:
    """Verify that unmanaged resource types are not touched."""

    def test_nodes_only_does_not_delete_clients(self) -> None:
        """Declaring only desired_nodes must NOT delete existing clients."""
        desired = DesiredState(
            nodes=[DesiredNodeState(host="198.51.100.1")],
            manage_nodes=True,
            manage_clients=False,
        )
        actual = ActualState(
            clients=["alice", "bob"],
        )
        plan = compute_plan(desired, actual)
        client_actions = [a for a in plan.actions if "client" in a.kind.value]
        assert len(client_actions) == 0

    def test_clients_only_does_not_delete_nodes(self) -> None:
        desired = DesiredState(
            clients=["alice"],
            manage_clients=True,
            manage_nodes=False,
        )
        actual = ActualState(
            nodes=[ActualNodeState(host="198.51.100.1")],
        )
        plan = compute_plan(desired, actual)
        node_actions = [a for a in plan.actions if "node" in a.kind.value]
        assert len(node_actions) == 0

    def test_unmanaged_relays_not_removed(self) -> None:
        desired = DesiredState(
            clients=["alice"],
            manage_clients=True,
            manage_relays=False,
        )
        actual = ActualState(
            relays=[ActualRelayState(host="198.51.100.10")],
        )
        plan = compute_plan(desired, actual)
        relay_actions = [a for a in plan.actions if "relay" in a.kind.value]
        assert len(relay_actions) == 0


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
            manage_nodes=True,
            manage_clients=True,
            manage_relays=True,
            manage_subscription_page=True,
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

    def test_symbol_update(self) -> None:
        action = PlanAction(kind=PlanActionKind.UPDATE_NODE, target="x")
        assert action.symbol == "~"

    def test_summary_with_adds_updates_and_removes(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_NODE, target="a"),
                PlanAction(kind=PlanActionKind.UPDATE_NODE, target="b"),
                PlanAction(kind=PlanActionKind.REMOVE_CLIENT, target="c", destructive=True),
            ]
        )
        assert "1 to add" in plan.summary()
        assert "1 to update" in plan.summary()
        assert "1 to remove" in plan.summary()


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
                PlanAction(kind=PlanActionKind.UPDATE_NODE, target="198.51.100.2", detail="sni changed"),
                PlanAction(kind=PlanActionKind.REMOVE_CLIENT, target="bob", detail="delete", destructive=True),
            ]
        )
        console = MagicMock()
        print_plan(plan, console=console)
        assert console.print.call_count >= 4  # actions + summary + warning


# ---------------------------------------------------------------------------
# build_desired_state
# ---------------------------------------------------------------------------


def _make_cluster(**kwargs):
    """Create a minimal ClusterConfig for testing."""
    from meridian.cluster import ClusterConfig, PanelConfig

    defaults = {
        "version": 2,
        "panel": PanelConfig(url="https://198.51.100.1/panel", api_token="tok", server_ip="198.51.100.1"),
    }
    defaults.update(kwargs)
    return ClusterConfig(**defaults)


class TestBuildDesiredState:
    def test_none_desired_fields_unmanaged(self) -> None:
        cluster = _make_cluster(desired_nodes=None, desired_clients=None, desired_relays=None)
        ds = build_desired_state(cluster)
        assert not ds.manage_nodes
        assert not ds.manage_clients
        assert not ds.manage_relays

    def test_empty_desired_fields_managed(self) -> None:
        cluster = _make_cluster(desired_nodes=[], desired_clients=[], desired_relays=[])
        ds = build_desired_state(cluster)
        assert ds.manage_nodes
        assert ds.manage_clients
        assert ds.manage_relays
        assert ds.nodes == []
        assert ds.clients == []

    def test_subscription_page_none_unmanaged(self) -> None:
        cluster = _make_cluster(subscription_page=None)
        ds = build_desired_state(cluster)
        assert not ds.manage_subscription_page

    def test_subscription_page_declared_managed(self) -> None:
        from meridian.cluster import SubscriptionPageConfig

        cluster = _make_cluster(subscription_page=SubscriptionPageConfig(enabled=True))
        ds = build_desired_state(cluster)
        assert ds.manage_subscription_page
        assert ds.subscription_page_enabled

    def test_desired_nodes_populated(self) -> None:
        from meridian.cluster import DesiredNode

        cluster = _make_cluster(desired_nodes=[DesiredNode(host="198.51.100.2", name="de-fra-1", sni="test.com")])
        ds = build_desired_state(cluster)
        assert len(ds.nodes) == 1
        assert ds.nodes[0].host == "198.51.100.2"
        assert ds.nodes[0].sni == "test.com"


# ---------------------------------------------------------------------------
# build_actual_state
# ---------------------------------------------------------------------------


def _mock_panel(nodes=None, users=None):
    """Create a mock MeridianPanel."""
    from meridian.remnawave import MeridianPanel

    panel = MagicMock(spec=MeridianPanel)
    panel.list_nodes.return_value = nodes or []
    panel.list_users.return_value = users or []
    return panel


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


class TestBuildActualState:
    def test_nodes_from_panel_api(self) -> None:
        from meridian.cluster import NodeEntry

        cluster = _make_cluster(nodes=[NodeEntry(ip="198.51.100.2", uuid="uuid-1", name="node-1")])
        panel = _mock_panel(nodes=[_ns(address="198.51.100.2", name="node-1", uuid="uuid-1", is_connected=True)])
        actual = build_actual_state(cluster, panel)
        assert len(actual.nodes) == 1
        assert actual.nodes[0].host == "198.51.100.2"
        assert actual.nodes[0].is_connected is True

    def test_docker_gateway_uuid_mapping(self) -> None:
        from meridian.cluster import NodeEntry

        cluster = _make_cluster(
            nodes=[NodeEntry(ip="198.51.100.1", uuid="uuid-panel", name="panel", is_panel_host=True)]
        )
        # Panel API returns node at Docker gateway address
        panel = _mock_panel(nodes=[_ns(address="172.17.0.1", name="panel", uuid="uuid-panel", is_connected=True)])
        actual = build_actual_state(cluster, panel)
        assert len(actual.nodes) == 1
        assert actual.nodes[0].host == "198.51.100.1"  # mapped back to public IP
        assert actual.nodes[0].is_panel_host is True

    def test_uuid_drift_private_ip_fallback(self) -> None:
        from meridian.cluster import NodeEntry

        cluster = _make_cluster(nodes=[NodeEntry(ip="198.51.100.1", uuid="old-uuid", name="panel", is_panel_host=True)])
        # Panel API returns node with NEW uuid at Docker gateway
        panel = _mock_panel(nodes=[_ns(address="172.17.0.1", name="panel", uuid="new-uuid", is_connected=True)])
        actual = build_actual_state(cluster, panel)
        assert len(actual.nodes) == 1
        assert actual.nodes[0].host == "198.51.100.1"  # private IP mapped to panel host
        assert actual.nodes[0].is_panel_host is True

    def test_panel_host_detection_by_server_ip(self) -> None:
        from meridian.cluster import NodeEntry

        cluster = _make_cluster(nodes=[NodeEntry(ip="198.51.100.1", uuid="uuid-1", name="node-1", is_panel_host=False)])
        panel = _mock_panel(nodes=[_ns(address="198.51.100.1", name="node-1", uuid="uuid-1", is_connected=True)])
        actual = build_actual_state(cluster, panel)
        # panel.server_ip matches → detected as panel host
        assert actual.nodes[0].is_panel_host is True

    def test_clients_from_panel(self) -> None:
        cluster = _make_cluster()
        panel = _mock_panel(users=[_ns(username="alice"), _ns(username="bob")])
        actual = build_actual_state(cluster, panel)
        assert actual.clients == ["alice", "bob"]

    def test_relay_sni_loaded(self) -> None:
        from meridian.cluster import RelayEntry

        cluster = _make_cluster(relays=[RelayEntry(ip="198.51.100.10", name="relay-1", sni="custom.sni.com")])
        panel = _mock_panel()
        actual = build_actual_state(cluster, panel)
        assert len(actual.relays) == 1
        assert actual.relays[0].sni == "custom.sni.com"

    def test_subscription_page_ssh_check(self) -> None:
        from meridian.cluster import NodeEntry, SubscriptionPageConfig
        from meridian.ssh import ServerConnection

        cluster = _make_cluster(
            nodes=[NodeEntry(ip="198.51.100.1", is_panel_host=True)],
            subscription_page=SubscriptionPageConfig(enabled=True),
        )
        panel = _mock_panel()
        conn = MagicMock(spec=ServerConnection)
        conn.run.return_value = _ns(returncode=0, stdout="true\n", stderr="")
        actual = build_actual_state(cluster, panel, panel_conn=conn)
        assert actual.subscription_page_running is True

    def test_subscription_page_ssh_failure_fallback(self) -> None:
        from meridian.cluster import SubscriptionPageConfig
        from meridian.ssh import ServerConnection

        cluster = _make_cluster(
            subscription_page=SubscriptionPageConfig(enabled=True, _extra={"deployed": True}),
        )
        panel = _mock_panel()
        conn = MagicMock(spec=ServerConnection)
        conn.run.side_effect = OSError("SSH connection refused")
        actual = build_actual_state(cluster, panel, panel_conn=conn)
        # Fallback to deployed flag
        assert actual.subscription_page_running is True
