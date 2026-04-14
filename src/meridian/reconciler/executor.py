"""Plan executor — runs reconciliation actions using existing provisioning.

Does NOT reimplement SSH provisioning or API calls. Instead, it calls
into the existing functions from ``commands/setup.py`` and ``provision/``.
Each action is executed in dependency order (nodes → relays → clients).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from meridian.reconciler.diff import Plan, PlanAction, PlanActionKind

logger = logging.getLogger("meridian.reconciler")


@dataclass
class ActionResult:
    """Result of executing a single plan action."""

    action: PlanAction
    success: bool = True
    error: str = ""


@dataclass
class ExecutionResult:
    """Result of executing an entire plan."""

    results: list[ActionResult] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        return all(r.success for r in self.results)

    @property
    def failed(self) -> list[ActionResult]:
        return [r for r in self.results if not r.success]

    def summary(self) -> str:
        succeeded = sum(1 for r in self.results if r.success)
        failed_count = len(self.failed)
        if failed_count == 0:
            return f"All {succeeded} action(s) completed successfully."
        return f"{succeeded} succeeded, {failed_count} failed."


def execute_plan(
    plan: Plan,
    panel: Any,
    cluster: Any,
    *,
    callbacks: dict[PlanActionKind, Any] | None = None,
) -> ExecutionResult:
    """Execute a reconciliation plan.

    Actions are run in dependency order: nodes first, then relays, then
    clients, then subscription page. Each action calls into existing
    provisioning code via callbacks.

    Args:
        plan: The reconciliation plan to execute.
        panel: MeridianPanel instance for API calls.
        cluster: ClusterConfig instance for state management.
        callbacks: Optional dict mapping action kinds to handler functions.
            Each handler receives (action, panel, cluster) and should
            return True on success or raise on failure.
    """
    callbacks = callbacks or {}
    results: list[ActionResult] = []

    # Execute in dependency order
    order = [
        PlanActionKind.ADD_NODE,
        PlanActionKind.ADD_RELAY,
        PlanActionKind.ADD_SUBSCRIPTION_PAGE,
        PlanActionKind.ADD_CLIENT,
        PlanActionKind.REMOVE_CLIENT,
        PlanActionKind.REMOVE_RELAY,
        PlanActionKind.REMOVE_SUBSCRIPTION_PAGE,
        PlanActionKind.REMOVE_NODE,
    ]

    # Group actions by kind, preserving order within each kind
    by_kind: dict[PlanActionKind, list[PlanAction]] = {}
    for action in plan.actions:
        by_kind.setdefault(action.kind, []).append(action)

    for kind in order:
        for action in by_kind.get(kind, []):
            handler = callbacks.get(action.kind)
            if handler is None:
                logger.warning("No handler for action kind: %s", action.kind)
                results.append(ActionResult(action=action, success=False, error="no handler registered"))
                continue

            try:
                handler(action, panel, cluster)
                results.append(ActionResult(action=action, success=True))
                logger.info("Action succeeded: %s %s", action.kind.value, action.target)
            except Exception as e:
                logger.error("Action failed: %s %s — %s", action.kind.value, action.target, e)
                results.append(ActionResult(action=action, success=False, error=str(e)))

    return ExecutionResult(results=results)
