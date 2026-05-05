"""Meridian core API primitives.

Core modules expose typed request/result/event contracts used by CLI, future
UI clients, and automation adapters. They must not depend on Typer command
parsing or Rich console state.
"""

from meridian.core.clients import ClientDetail, ClientListResult, ClientListSummary, ClientRecord, ClientShowResult
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
from meridian.core.output import (
    EventStream,
    OperationContext,
    command_envelope,
    envelope,
    json_dumps,
    jsonl_dumps,
    plan_payload,
)
from meridian.core.plan import PlanActionResult, PlanCounts, PlanResult, build_plan_result
from meridian.core.redaction import REDACTED, redact
from meridian.core.schema import (
    ApiCommandsResult,
    ApiSchemaResult,
    ApiSchemasResult,
    CommandContract,
    EmptyData,
    command_catalog,
    command_contracts,
    schema_catalog,
    schema_for,
    schema_names,
    validate_command_envelope,
)
from meridian.core.services import (
    ClientListServiceResult,
    ClientNotFoundError,
    ClientShowServiceResult,
    FleetInventoryServiceResult,
    FleetStatusServiceResult,
    collect_client_list,
    collect_client_show,
    collect_fleet_inventory,
    collect_fleet_status,
)

__all__ = [
    "EventStream",
    "OperationContext",
    "ApiCommandsResult",
    "ApiSchemaResult",
    "ApiSchemasResult",
    "ClientDetail",
    "ClientListResult",
    "ClientListServiceResult",
    "ClientListSummary",
    "ClientNotFoundError",
    "ClientRecord",
    "ClientShowResult",
    "ClientShowServiceResult",
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
    "collect_client_list",
    "collect_client_show",
    "command_envelope",
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
    "validate_command_envelope",
]
