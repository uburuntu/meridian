"""Deploy service boundary for CLI and future UI clients."""

from __future__ import annotations

from collections.abc import Callable

from meridian.core.deploy import DeployRequest, DeployResult
from meridian.core.output import OperationContext
from meridian.core.reporters import NoopReporter, Reporter, emit_event

DeployExecutor = Callable[[DeployRequest, Reporter, OperationContext], DeployResult]


def deploy_server(
    request: DeployRequest,
    *,
    executor: DeployExecutor,
    reporter: Reporter | None = None,
    operation: OperationContext | None = None,
) -> DeployResult:
    """Run a deploy through the core service boundary.

    The executor is injected so CLI adapters can migrate orchestration
    incrementally without letting core import command modules.
    """
    operation = operation or OperationContext()
    reporter = reporter or NoopReporter()
    emit_event(
        reporter,
        operation,
        "command.started",
        phase="deploy",
        message="Deploy started",
        data={"command": "deploy"},
    )
    try:
        result = executor(request, reporter, operation)
    except Exception as exc:
        emit_event(
            reporter,
            operation,
            "command.failed",
            level="error",
            phase="deploy",
            message=str(exc),
            data={"command": "deploy", "cause": type(exc).__name__},
        )
        raise
    emit_event(
        reporter,
        operation,
        "command.completed",
        phase="deploy",
        message=result.summary,
        data={"command": "deploy", "mode": result.mode, "server_ip": result.server_ip},
    )
    return result
