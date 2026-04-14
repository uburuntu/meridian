"""Plan executor — runs reconciliation actions using existing provisioning.

Does NOT reimplement SSH provisioning or API calls. Instead, it calls
into the existing functions from ``commands/setup.py`` and ``provision/``.
Each action is executed in dependency order (nodes → relays → clients).

Node provisioning is parallelized when multiple nodes are independent.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _run_action(
    action: PlanAction,
    handler: Any,
    panel: Any,
    cluster: Any,
) -> ActionResult:
    """Execute a single action and return the result."""
    try:
        handler(action, panel, cluster)
        logger.info("Action succeeded: %s %s", action.kind.value, action.target)
        return ActionResult(action=action, success=True)
    except Exception as e:
        logger.error("Action failed: %s %s — %s", action.kind.value, action.target, e)
        return ActionResult(action=action, success=False, error=str(e))


def execute_plan(
    plan: Plan,
    panel: Any,
    cluster: Any,
    *,
    callbacks: dict[PlanActionKind, Any] | None = None,
    max_parallel: int = 4,
) -> ExecutionResult:
    """Execute a reconciliation plan.

    Actions are run in dependency order: nodes first, then relays, then
    clients, then subscription page. Node ADD actions within the same
    phase are parallelized (each node is independent).

    Args:
        plan: The reconciliation plan to execute.
        panel: MeridianPanel instance for API calls.
        cluster: ClusterConfig instance for state management.
        callbacks: Optional dict mapping action kinds to handler functions.
            Each handler receives (action, panel, cluster) and should
            return True on success or raise on failure.
        max_parallel: Maximum number of concurrent node provisioning threads.
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

    # Kinds that can be parallelized (independent per-server operations)
    parallel_kinds = {PlanActionKind.ADD_NODE}

    # Group actions by kind, preserving order within each kind
    by_kind: dict[PlanActionKind, list[PlanAction]] = {}
    for action in plan.actions:
        by_kind.setdefault(action.kind, []).append(action)

    for kind in order:
        actions = by_kind.get(kind, [])
        if not actions:
            continue

        handler = callbacks.get(kind)
        if handler is None:
            for action in actions:
                logger.warning("No handler for action kind: %s", kind)
                results.append(ActionResult(action=action, success=False, error="no handler registered"))
            continue

        # Parallelize independent actions (e.g., node provisioning)
        if kind in parallel_kinds and len(actions) > 1 and max_parallel > 1:
            with ThreadPoolExecutor(max_workers=min(max_parallel, len(actions))) as pool:
                futures = {pool.submit(_run_action, action, handler, panel, cluster): action for action in actions}
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for action in actions:
                results.append(_run_action(action, handler, panel, cluster))

    return ExecutionResult(results=results)
