"""Apply result contracts for meridian-core clients."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from meridian.core.models import CoreModel
from meridian.core.plan import PlanActionResult, PlanResult, build_plan_action_result, build_plan_result

ApplyActionStatus = Literal["succeeded", "failed", "skipped"]


class ApplyActionResult(CoreModel):
    """Execution result for one plan action."""

    action: PlanActionResult
    status: ApplyActionStatus
    success: bool
    error: str = ""


class ApplyCounts(CoreModel):
    """Aggregate counts for apply execution."""

    actions: int
    succeeded: int
    failed: int
    skipped: int


class ApplyResult(CoreModel):
    """Final apply result for process/API clients."""

    all_succeeded: bool
    summary: str
    exit_code: int
    plan: PlanResult
    counts: ApplyCounts
    actions: list[ApplyActionResult] = Field(default_factory=list)

    def to_data(self) -> dict[str, Any]:
        from meridian.core.serde import to_plain

        return to_plain(self)


def _apply_status(result: Any) -> ApplyActionStatus:
    if result.success:
        return "succeeded"
    if str(result.error).lower().startswith("skipped"):
        return "skipped"
    return "failed"


def build_apply_result(plan: Any, execution_result: Any, *, exit_code: int) -> ApplyResult:
    """Build a typed, JSON-ready apply result from executor output."""
    raw_actions = list(plan.actions)
    plan_index_by_id = {id(action): index for index, action in enumerate(raw_actions)}
    execution_order = {id(result.action): index for index, result in enumerate(execution_result.results, start=1)}
    actions = []
    for fallback_index, result in enumerate(execution_result.results):
        plan_index = plan_index_by_id.get(id(result.action), fallback_index)
        status = _apply_status(result)
        actions.append(
            ApplyActionResult(
                action=build_plan_action_result(
                    result.action,
                    plan_index=plan_index,
                    execution_order=execution_order[id(result.action)],
                ),
                status=status,
                success=result.success,
                error=result.error,
            )
        )
    counts = ApplyCounts(
        actions=len(actions),
        succeeded=sum(1 for action in actions if action.status == "succeeded"),
        failed=sum(1 for action in actions if action.status == "failed"),
        skipped=sum(1 for action in actions if action.status == "skipped"),
    )
    return ApplyResult(
        all_succeeded=execution_result.all_succeeded,
        summary=execution_result.summary(),
        exit_code=exit_code,
        plan=build_plan_result(plan, exit_code=0 if plan.is_empty else 2),
        counts=counts,
        actions=actions,
    )
