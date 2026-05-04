"""Tests for meridian-core JSON Schema catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meridian.core.models import MeridianError
from meridian.core.output import OperationTimer, envelope
from meridian.core.schema import PlanOutputEnvelope, command_catalog, schema_catalog, schema_for, schema_names


def test_schema_catalog_lists_public_contracts() -> None:
    names = schema_names()

    assert "output-envelope" in names
    assert "plan-envelope" in names
    assert "fleet-status-envelope" in names
    assert "fleet-inventory-envelope" in names
    assert "event" in names
    assert "command-contract" in names
    assert "empty-data" in names
    assert "plan-result" in names
    assert "fleet-status" in names
    assert "fleet-inventory" in names


def test_schema_for_output_envelope_uses_wire_aliases() -> None:
    schema = schema_for("output-envelope")

    assert "schema" in schema["properties"]
    assert "schema_version" not in schema["properties"]
    assert schema["properties"]["status"]["enum"] == ["ok", "changed", "no_changes", "failed", "cancelled"]


def test_command_envelope_schema_binds_command_to_typed_data() -> None:
    schema = schema_for("fleet-status-envelope")

    assert schema["properties"]["command"]["const"] == "fleet.status"
    data_schema = schema["properties"]["data"]
    refs = [option["$ref"] for option in data_schema["anyOf"]]
    assert any(ref.endswith("/FleetStatus") for ref in refs)
    assert any(ref.endswith("/EmptyData") for ref in refs)


def test_schema_catalog_can_include_full_schemas() -> None:
    catalog = schema_catalog(include_schemas=True)
    output = next(item for item in catalog if item["name"] == "output-envelope")
    plan = next(item for item in catalog if item["name"] == "plan-envelope")

    assert output["title"] == "OutputEnvelope"
    assert output["schema"]["properties"]["command"]["type"] == "string"
    assert plan["commands"] == ["plan"]


def test_command_catalog_maps_commands_to_envelope_and_data_schemas() -> None:
    catalog = command_catalog()
    by_command = {item["command"]: item for item in catalog}

    assert by_command["plan"]["envelope_schema"] == "plan-envelope"
    assert by_command["plan"]["data_schema"] == "plan-result"
    assert by_command["plan"]["failure_data_schema"] == "empty-data"
    assert by_command["plan"]["error_schema"] == "error"
    assert by_command["plan"]["machine_flags"] == ["--json"]
    assert "changed" in by_command["plan"]["statuses"]
    assert by_command["fleet.status"]["data_schema"] == "fleet-status"
    assert by_command["fleet.inventory"]["statuses"] == ["ok", "failed", "cancelled"]
    assert by_command["fleet.inventory"]["exit_codes"]["130"] == "cancelled by the user"


def test_command_catalog_can_embed_command_schemas() -> None:
    catalog = command_catalog(include_schemas=True)
    plan = next(item for item in catalog if item["command"] == "plan")

    assert plan["envelope"]["properties"]["command"]["const"] == "plan"
    assert plan["data"]["title"] == "PlanResult"


def test_command_envelope_schema_validates_failed_output_shape() -> None:
    error = MeridianError(
        code="MERIDIAN_USER_ERROR",
        category="user",
        message="No desired state defined in cluster.yml",
        exit_code=2,
    )
    payload = envelope(
        command="plan",
        summary="No desired state defined in cluster.yml",
        status="failed",
        exit_code=2,
        errors=[error],
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )

    parsed = PlanOutputEnvelope.model_validate(payload.model_dump(mode="json", by_alias=True))

    assert parsed.command == "plan"
    assert parsed.status == "failed"
    assert parsed.data.model_dump() == {}


def test_command_envelope_schema_rejects_failed_output_without_error() -> None:
    payload = envelope(
        command="plan",
        summary="No desired state defined in cluster.yml",
        status="failed",
        exit_code=2,
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )

    with pytest.raises(ValidationError, match="requires at least one error"):
        PlanOutputEnvelope.model_validate(payload.model_dump(mode="json", by_alias=True))


def test_command_envelope_schema_rejects_success_without_typed_data() -> None:
    payload = envelope(
        command="plan",
        summary="Plan has changes",
        status="changed",
        exit_code=2,
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )

    with pytest.raises(ValidationError, match="requires typed data"):
        PlanOutputEnvelope.model_validate(payload.model_dump(mode="json", by_alias=True))


def test_unknown_schema_name_is_actionable() -> None:
    with pytest.raises(ValueError, match="Available:"):
        schema_for("missing")
