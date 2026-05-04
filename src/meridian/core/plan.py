"""Plan result contracts for meridian-core clients."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from meridian.core.models import CoreModel


class PlanActionResult(CoreModel):
    kind: str
    target: str
    detail: str
    destructive: bool
    from_extras: bool
    symbol: str


class PlanCounts(CoreModel):
    actions: int
    adds: int
    updates: int
    removes: int
    destructive: int
    from_extras: int


class PlanResult(CoreModel):
    converged: bool
    summary: str
    exit_code: int
    counts: PlanCounts
    actions: list[PlanActionResult] = Field(default_factory=list)

    def to_data(self) -> dict[str, Any]:
        from meridian.core.serde import to_plain

        return to_plain(self)


def build_plan_result(plan: Any, *, exit_code: int) -> PlanResult:
    """Build a typed, JSON-ready plan result from the reconciler plan."""
    actions = [
        PlanActionResult(
            kind=action.kind.value,
            target=action.target,
            detail=action.detail,
            destructive=action.destructive,
            from_extras=action.from_extras,
            symbol=action.symbol,
        )
        for action in plan.actions
    ]
    counts = PlanCounts(
        actions=len(actions),
        adds=sum(1 for action in actions if action.symbol == "+"),
        updates=sum(1 for action in actions if action.symbol == "~"),
        removes=sum(1 for action in actions if action.symbol == "-"),
        destructive=sum(1 for action in actions if action.destructive),
        from_extras=sum(1 for action in actions if action.from_extras),
    )
    return PlanResult(
        converged=plan.is_empty,
        summary=plan.summary(),
        exit_code=exit_code,
        counts=counts,
        actions=actions,
    )
