"""Plan result contracts for meridian-core clients."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import Field

from meridian.core.models import CoreModel

PlanOperation = Literal["add", "update", "remove"]
PlanResourceType = Literal["node", "client", "relay", "subscription_page"]
PlanPhase = Literal["provision", "configure", "deprovision"]
PlanSymbol = Literal["+", "~", "-"]
PlanActionKindValue = Literal[
    "add_node",
    "update_node",
    "remove_node",
    "add_client",
    "remove_client",
    "add_relay",
    "update_relay",
    "remove_relay",
    "add_subscription_page",
    "remove_subscription_page",
]


class PlanChange(CoreModel):
    field: str
    before: str
    after: str


class PlanActionResult(CoreModel):
    kind: PlanActionKindValue
    operation: PlanOperation
    resource_type: PlanResourceType
    resource_id: str
    target: str
    detail: str
    destructive: bool
    from_extras: bool
    phase: PlanPhase
    requires_confirmation: bool
    destructive_reason: str
    change_set: list[PlanChange] = Field(default_factory=list)
    symbol: PlanSymbol


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


def _operation(kind: str) -> PlanOperation:
    if kind.startswith("add_"):
        return "add"
    if kind.startswith("remove_"):
        return "remove"
    return "update"


def _resource_type(kind: str) -> PlanResourceType:
    if kind.endswith("_node"):
        return "node"
    if kind.endswith("_client"):
        return "client"
    if kind.endswith("_relay"):
        return "relay"
    return "subscription_page"


def _phase(operation: PlanOperation) -> PlanPhase:
    if operation == "add":
        return "provision"
    if operation == "remove":
        return "deprovision"
    return "configure"


def _symbol(operation: PlanOperation) -> PlanSymbol:
    if operation == "add":
        return "+"
    if operation == "remove":
        return "-"
    return "~"


def build_plan_result(plan: Any, *, exit_code: int) -> PlanResult:
    """Build a typed, JSON-ready plan result from the reconciler plan."""
    actions = []
    for action in plan.actions:
        kind = cast(PlanActionKindValue, action.kind.value)
        operation = _operation(kind)
        actions.append(
            PlanActionResult(
                kind=kind,
                operation=operation,
                resource_type=_resource_type(kind),
                resource_id=action.target,
                target=action.target,
                detail=action.detail,
                destructive=action.destructive,
                from_extras=action.from_extras,
                phase=_phase(operation),
                requires_confirmation=action.destructive,
                destructive_reason=action.detail if action.destructive else "",
                change_set=[
                    PlanChange(field=change.field, before=change.before, after=change.after)
                    for change in getattr(action, "changes", [])
                ],
                symbol=_symbol(operation),
            )
        )
    counts = PlanCounts(
        actions=len(actions),
        adds=sum(1 for action in actions if action.operation == "add"),
        updates=sum(1 for action in actions if action.operation == "update"),
        removes=sum(1 for action in actions if action.operation == "remove"),
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
