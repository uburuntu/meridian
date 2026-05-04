"""JSON Schema catalog for meridian-core contracts."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from meridian.core.fleet import FleetInventory, FleetStatus
from meridian.core.models import CoreModel, Event, MeridianError, OutputEnvelope, OutputStatus, Summary
from meridian.core.plan import PlanActionResult, PlanCounts, PlanResult


class EmptyData(CoreModel):
    """Empty data object used by failed or cancelled envelopes."""


class PlanOutputEnvelope(OutputEnvelope):
    """Envelope schema for `meridian plan --json`."""

    command: Literal["plan"] = "plan"
    data: PlanResult | EmptyData = Field(default_factory=EmptyData)  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_command_shape(self) -> Self:
        _validate_envelope_shape(self, success_statuses={"changed", "no_changes"})
        return self


class FleetStatusOutputEnvelope(OutputEnvelope):
    """Envelope schema for `meridian fleet status --json`."""

    command: Literal["fleet.status"] = "fleet.status"
    data: FleetStatus | EmptyData = Field(default_factory=EmptyData)  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_command_shape(self) -> Self:
        _validate_envelope_shape(self, success_statuses={"ok"})
        return self


class FleetInventoryOutputEnvelope(OutputEnvelope):
    """Envelope schema for `meridian fleet inventory --json`."""

    command: Literal["fleet.inventory"] = "fleet.inventory"
    data: FleetInventory | EmptyData = Field(default_factory=EmptyData)  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_command_shape(self) -> Self:
        _validate_envelope_shape(self, success_statuses={"ok"})
        return self


def _validate_envelope_shape(envelope: OutputEnvelope, *, success_statuses: set[OutputStatus]) -> None:
    """Keep command-specific envelopes internally consistent."""
    terminal_statuses: set[OutputStatus] = {*success_statuses, "failed", "cancelled"}
    if envelope.status not in terminal_statuses:
        raise ValueError(f"{envelope.command} does not support status {envelope.status!r}")

    is_success = envelope.status in success_statuses
    has_empty_data = isinstance(envelope.data, EmptyData)
    if is_success:
        if has_empty_data:
            raise ValueError(f"{envelope.command} status {envelope.status!r} requires typed data")
        if envelope.errors:
            raise ValueError(f"{envelope.command} status {envelope.status!r} cannot include errors")
        return

    if not has_empty_data:
        raise ValueError(f"{envelope.command} status {envelope.status!r} requires empty data")
    if not envelope.errors:
        raise ValueError(f"{envelope.command} status {envelope.status!r} requires at least one error")


class CommandContract(CoreModel):
    """Discoverable command-to-schema contract for process API clients."""

    command: str
    envelope_schema: str
    data_schema: str
    failure_data_schema: str
    error_schema: str
    statuses: list[OutputStatus]
    exit_codes: dict[str, str]
    machine_flags: list[str]
    stability: Literal["stable", "preview"]
    description: str


_SCHEMAS: dict[str, type[CoreModel]] = {
    "output-envelope": OutputEnvelope,
    "plan-envelope": PlanOutputEnvelope,
    "fleet-status-envelope": FleetStatusOutputEnvelope,
    "fleet-inventory-envelope": FleetInventoryOutputEnvelope,
    "event": Event,
    "error": MeridianError,
    "summary": Summary,
    "empty-data": EmptyData,
    "plan-result": PlanResult,
    "plan-action": PlanActionResult,
    "plan-counts": PlanCounts,
    "fleet-status": FleetStatus,
    "fleet-inventory": FleetInventory,
    "command-contract": CommandContract,
}

_COMMAND_CONTRACTS: dict[str, CommandContract] = {
    "plan": CommandContract(
        command="plan",
        envelope_schema="plan-envelope",
        data_schema="plan-result",
        failure_data_schema="empty-data",
        error_schema="error",
        statuses=["no_changes", "changed", "failed", "cancelled"],
        exit_codes={
            "0": "desired state already matches actual state",
            "2": "changes pending; user/config errors also use category=user in the error envelope",
            "3": "system or infrastructure failure",
            "130": "cancelled by the user",
        },
        machine_flags=["--json"],
        stability="stable",
        description="Compute the desired-state reconciliation plan without applying it.",
    ),
    "fleet.status": CommandContract(
        command="fleet.status",
        envelope_schema="fleet-status-envelope",
        data_schema="fleet-status",
        failure_data_schema="empty-data",
        error_schema="error",
        statuses=["ok", "failed", "cancelled"],
        exit_codes={
            "0": "fleet status was collected; inspect data.summary.health and warnings for degraded state",
            "2": "user/config error",
            "3": "system or infrastructure failure",
            "130": "cancelled by the user",
        },
        machine_flags=["--json"],
        stability="stable",
        description="Collect panel, node, relay, and user health observations for the configured fleet.",
    ),
    "fleet.inventory": CommandContract(
        command="fleet.inventory",
        envelope_schema="fleet-inventory-envelope",
        data_schema="fleet-inventory",
        failure_data_schema="empty-data",
        error_schema="error",
        statuses=["ok", "failed", "cancelled"],
        exit_codes={
            "0": "inventory was collected; plan --json is the drift/apply authority",
            "2": "user/config error",
            "3": "system or infrastructure failure",
            "130": "cancelled by the user",
        },
        machine_flags=["--json"],
        stability="stable",
        description="Return the configured fleet topology plus live panel observations when available.",
    ),
}

_COMMAND_SCHEMAS: dict[str, str] = {
    command: contract.envelope_schema for command, contract in _COMMAND_CONTRACTS.items()
}


def schema_names() -> list[str]:
    """Return stable schema names."""
    return sorted(_SCHEMAS)


def schema_model(name: str) -> type[CoreModel]:
    """Return the Pydantic model for a stable schema name."""
    try:
        return _SCHEMAS[name]
    except KeyError as exc:
        available = ", ".join(schema_names())
        raise ValueError(f"Unknown schema {name!r}. Available: {available}") from exc


def schema_for(name: str) -> dict[str, Any]:
    """Return JSON Schema for one meridian-core contract."""
    return schema_model(name).model_json_schema(mode="serialization", by_alias=True)


def schema_catalog(*, include_schemas: bool = False) -> list[dict[str, Any]]:
    """Return schema metadata, optionally including full JSON Schemas."""
    catalog = []
    for name in schema_names():
        model = schema_model(name)
        item: dict[str, Any] = {
            "name": name,
            "title": model.__name__,
            "description": (model.__doc__ or "").strip(),
        }
        commands = [command for command, schema_name in _COMMAND_SCHEMAS.items() if schema_name == name]
        if commands:
            item["commands"] = commands
        if include_schemas:
            item["schema"] = schema_for(name)
        catalog.append(item)
    return catalog


def command_contracts() -> list[CommandContract]:
    """Return stable command contracts for migrated process API commands."""
    return [_COMMAND_CONTRACTS[name] for name in sorted(_COMMAND_CONTRACTS)]


def command_catalog(*, include_schemas: bool = False) -> list[dict[str, Any]]:
    """Return command contract metadata, optionally including JSON Schemas."""
    catalog: list[dict[str, Any]] = []
    for contract in command_contracts():
        item: dict[str, Any] = contract.model_dump(mode="json")
        if include_schemas:
            item["envelope"] = schema_for(contract.envelope_schema)
            item["data"] = schema_for(contract.data_schema)
        catalog.append(item)
    return catalog
