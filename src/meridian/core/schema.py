"""JSON Schema catalog for meridian-core contracts."""

from __future__ import annotations

from typing import Any

from meridian.core.fleet import FleetInventory, FleetStatus
from meridian.core.models import CoreModel, Event, MeridianError, OutputEnvelope, Summary
from meridian.core.plan import PlanActionResult, PlanCounts, PlanResult

_SCHEMAS: dict[str, type[CoreModel]] = {
    "output-envelope": OutputEnvelope,
    "event": Event,
    "error": MeridianError,
    "summary": Summary,
    "plan-result": PlanResult,
    "plan-action": PlanActionResult,
    "plan-counts": PlanCounts,
    "fleet-status": FleetStatus,
    "fleet-inventory": FleetInventory,
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
        if include_schemas:
            item["schema"] = schema_for(name)
        catalog.append(item)
    return catalog
