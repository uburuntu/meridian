"""Tests for `meridian plan --json`.

The text-mode plan output is verified by the system lab (Stage 9) and by
TestDisplay in test_reconciler.py. These tests cover the JSON serialization
path used by CI/CD pipelines that need to gate on plan output.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
import typer

from meridian.cluster import ClusterConfig, NodeEntry, PanelConfig
from meridian.commands.plan import run as plan_run
from meridian.reconciler.diff import ActionChange, Plan, PlanAction, PlanActionKind


def _configured_cluster_with_desired() -> ClusterConfig:
    return ClusterConfig(
        version=2,
        panel=PanelConfig(
            url="https://198.51.100.1/panel",
            api_token="tok",
            server_ip="198.51.100.1",
        ),
        nodes=[NodeEntry(ip="198.51.100.1", uuid="u-1", name="exit-1", is_panel_host=True)],
        desired_clients=["alice"],
    )


def _capture_plan_json(plan: Plan) -> tuple[dict, int]:
    """Run plan command in --json mode against a stubbed plan; return (parsed_json, exit_code)."""
    cluster = _configured_cluster_with_desired()
    buf = io.StringIO()
    with (
        patch.object(ClusterConfig, "load", return_value=cluster),
        patch("meridian.remnawave.MeridianPanel"),
        patch("meridian.ssh.ServerConnection"),
        patch("meridian.commands.plan.build_desired_state"),
        patch("meridian.commands.plan.build_actual_state"),
        patch("meridian.commands.plan.compute_plan", return_value=plan),
        redirect_stdout(buf),
    ):
        with pytest.raises(typer.Exit) as exc_info:
            plan_run(json_output=True)
    return json.loads(buf.getvalue()), exc_info.value.exit_code


class TestPlanJsonOutput:
    def test_empty_plan_emits_converged_true_and_exit_zero(self) -> None:
        payload, exit_code = _capture_plan_json(Plan(actions=[]))
        assert payload["schema"] == "meridian.output/v1"
        assert payload["command"] == "plan"
        assert payload["status"] == "no_changes"
        assert payload["summary"]["changed"] is False
        assert payload["summary"]["counts"] == {
            "actions": 0,
            "adds": 0,
            "updates": 0,
            "removes": 0,
            "destructive": 0,
            "from_extras": 0,
        }
        assert payload["data"]["converged"] is True
        assert payload["data"]["actions"] == []
        assert payload["data"]["exit_code"] == 0
        assert exit_code == 0

    def test_non_empty_plan_emits_actions_and_exit_two(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(kind=PlanActionKind.ADD_CLIENT, target="alice", detail="create client alice"),
                PlanAction(
                    kind=PlanActionKind.REMOVE_CLIENT,
                    target="ghost",
                    detail="delete client ghost",
                    destructive=True,
                    from_extras=True,
                ),
            ]
        )
        payload, exit_code = _capture_plan_json(plan)
        assert payload["schema"] == "meridian.output/v1"
        assert payload["command"] == "plan"
        assert payload["status"] == "changed"
        assert payload["summary"]["changed"] is True
        assert payload["data"]["converged"] is False
        assert payload["data"]["exit_code"] == 2
        assert exit_code == 2
        assert len(payload["data"]["actions"]) == 2
        # ADD_CLIENT entry
        add = next(a for a in payload["data"]["actions"] if a["kind"] == "add_client")
        assert add["target"] == "alice"
        assert add["operation"] == "add"
        assert add["resource_type"] == "client"
        assert add["resource_id"] == "alice"
        assert add["phase"] == "provision"
        assert add["requires_confirmation"] is False
        assert add["destructive"] is False
        assert add["from_extras"] is False
        assert add["destructive_reason"] == ""
        assert add["change_set"] == []
        assert add["symbol"] == "+"
        # REMOVE_CLIENT entry — extras flag preserved for downstream tooling
        rm = next(a for a in payload["data"]["actions"] if a["kind"] == "remove_client")
        assert rm["target"] == "ghost"
        assert rm["operation"] == "remove"
        assert rm["resource_type"] == "client"
        assert rm["resource_id"] == "ghost"
        assert rm["phase"] == "deprovision"
        assert rm["requires_confirmation"] is True
        assert rm["destructive"] is True
        assert rm["destructive_reason"] == "delete client ghost"
        assert rm["from_extras"] is True
        assert rm["symbol"] == "-"

    def test_payload_is_valid_json_with_indentation(self) -> None:
        """Output should be human-readable (indented) AND machine-parseable.

        Some CI scripts pipe to `jq` directly; some `cat` it. Both need
        valid JSON; humans want to read it without `jq`.
        """
        plan = Plan(actions=[PlanAction(kind=PlanActionKind.ADD_CLIENT, target="x")])
        cluster = _configured_cluster_with_desired()
        buf = io.StringIO()
        with (
            patch.object(ClusterConfig, "load", return_value=cluster),
            patch("meridian.remnawave.MeridianPanel"),
            patch("meridian.ssh.ServerConnection"),
            patch("meridian.commands.plan.build_desired_state"),
            patch("meridian.commands.plan.build_actual_state"),
            patch("meridian.commands.plan.compute_plan", return_value=plan),
            redirect_stdout(buf),
        ):
            with pytest.raises(typer.Exit):
                plan_run(json_output=True)
        raw = buf.getvalue()
        # Indented = contains a newline before the first action key
        assert "\n" in raw
        # Parses as JSON
        json.loads(raw)

    def test_update_plan_action_includes_structured_change_set(self) -> None:
        plan = Plan(
            actions=[
                PlanAction(
                    kind=PlanActionKind.UPDATE_NODE,
                    target="198.51.100.2",
                    detail="redeploy node exit-b: sni: old.example → new.example",
                    changes=[ActionChange("sni", "old.example", "new.example")],
                )
            ]
        )

        payload, exit_code = _capture_plan_json(plan)

        action = payload["data"]["actions"][0]
        assert exit_code == 2
        assert action["kind"] == "update_node"
        assert action["operation"] == "update"
        assert action["change_set"] == [{"field": "sni", "before": "old.example", "after": "new.example"}]
