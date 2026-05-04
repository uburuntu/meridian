"""Meridian core API primitives.

Core modules expose typed request/result/event contracts used by CLI, future
UI clients, and automation adapters. They must not depend on Typer command
parsing or Rich console state.
"""

from meridian.core.fleet import FleetInventory, FleetSources, FleetStatus, FleetTopology, RelayHostRef
from meridian.core.models import (
    CoreModel,
    ErrorCategory,
    Event,
    EventLevel,
    MeridianError,
    OutputEnvelope,
    OutputStatus,
    ResourceRef,
    Summary,
)
from meridian.core.output import EventStream, OperationContext, envelope, json_dumps, jsonl_dumps, plan_payload
from meridian.core.plan import PlanActionResult, PlanCounts, PlanResult, build_plan_result
from meridian.core.redaction import REDACTED, redact
from meridian.core.schema import (
    CommandContract,
    EmptyData,
    command_catalog,
    command_contracts,
    schema_catalog,
    schema_for,
    schema_names,
)
from meridian.core.services import (
    FleetInventoryServiceResult,
    FleetStatusServiceResult,
    collect_fleet_inventory,
    collect_fleet_status,
)

__all__ = [
    "EventStream",
    "OperationContext",
    "CoreModel",
    "ErrorCategory",
    "Event",
    "EventLevel",
    "FleetInventory",
    "FleetInventoryServiceResult",
    "FleetSources",
    "FleetStatus",
    "FleetStatusServiceResult",
    "FleetTopology",
    "MeridianError",
    "OutputEnvelope",
    "OutputStatus",
    "PlanActionResult",
    "PlanCounts",
    "PlanResult",
    "REDACTED",
    "ResourceRef",
    "RelayHostRef",
    "Summary",
    "CommandContract",
    "EmptyData",
    "command_catalog",
    "command_contracts",
    "collect_fleet_inventory",
    "collect_fleet_status",
    "envelope",
    "json_dumps",
    "jsonl_dumps",
    "plan_payload",
    "redact",
    "build_plan_result",
    "schema_catalog",
    "schema_for",
    "schema_names",
]
