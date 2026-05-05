"""Tests for meridian-core deploy service boundary."""

from __future__ import annotations

import pytest

from meridian.core.deploy import DeployRequest, DeployResult
from meridian.core.output import OperationContext
from meridian.core.reporters import CaptureReporter
from meridian.core.services.deploy import deploy_server


def _result() -> DeployResult:
    return DeployResult(
        mode="first_deploy",
        server_ip="198.51.100.10",
        ssh_user="root",
        ssh_port=22,
        domain="",
        sni="www.microsoft.com",
        client_name="default",
        harden=True,
        pq=False,
        warp=False,
        geo_block=True,
        panel_url="https://198.51.100.10/panel/",
        panel_secret_path="secret",
        connection_page_path="page",
        node_count=1,
        relay_count=0,
        summary="Deploy completed for 198.51.100.10",
    )


def test_deploy_server_emits_lifecycle_events() -> None:
    request = DeployRequest(ip="198.51.100.10", yes=True)
    reporter = CaptureReporter()
    operation = OperationContext(operation_id="op-deploy", started_at="2026-05-04T21:00:00Z")
    seen: dict[str, object] = {}

    def executor(req: DeployRequest, rep: object, op: OperationContext) -> DeployResult:
        seen["request"] = req
        seen["reporter"] = rep
        seen["operation"] = op
        return _result()

    result = deploy_server(request, executor=executor, reporter=reporter, operation=operation)

    assert result.server_ip == "198.51.100.10"
    assert seen == {"request": request, "reporter": reporter, "operation": operation}
    assert [event.type for event in reporter.events] == ["command.started", "command.completed"]
    assert {event.operation_id for event in reporter.events} == {"op-deploy"}
    assert reporter.events[-1].data["mode"] == "first_deploy"


def test_deploy_server_emits_failure_event() -> None:
    request = DeployRequest(ip="198.51.100.10", yes=True)
    reporter = CaptureReporter()

    def executor(_req: DeployRequest, _rep: object, _op: OperationContext) -> DeployResult:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        deploy_server(request, executor=executor, reporter=reporter)

    assert [event.type for event in reporter.events] == ["command.started", "command.failed"]
    assert reporter.events[-1].level == "error"
    assert reporter.events[-1].data["cause"] == "RuntimeError"
