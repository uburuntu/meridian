"""Tests for meridian-core JSON Schema catalog."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meridian.core.clients import build_client_list_result
from meridian.core.models import MeridianError
from meridian.core.output import OperationTimer, command_envelope, envelope
from meridian.core.schema import (
    ApiCommandsResult,
    ApiSchemasResult,
    PlanOutputEnvelope,
    command_catalog,
    schema_catalog,
    schema_for,
    schema_names,
)


def test_schema_catalog_lists_public_contracts() -> None:
    names = schema_names()

    assert "output-envelope" in names
    assert "api-commands-envelope" in names
    assert "api-schema-envelope" in names
    assert "api-schemas-envelope" in names
    assert "client-list-envelope" in names
    assert "client-show-envelope" in names
    assert "plan-envelope" in names
    assert "fleet-status-envelope" in names
    assert "fleet-inventory-envelope" in names
    assert "event" in names
    assert "schema-catalog-entry" in names
    assert "command-contract" in names
    assert "command-catalog-entry" in names
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

    assert schema["discriminator"]["propertyName"] == "status"
    assert len(schema["oneOf"]) == 2
    refs = [option["$ref"] for option in schema["oneOf"]]
    success_ref = next(ref for ref in refs if ref.endswith("/_FleetStatusSuccessEnvelope"))
    terminal_ref = next(ref for ref in refs if ref.endswith("/_FleetStatusTerminalEnvelope"))
    success = schema["$defs"][success_ref.rsplit("/", 1)[-1]]
    terminal = schema["$defs"][terminal_ref.rsplit("/", 1)[-1]]
    assert success["properties"]["command"]["const"] == "fleet.status"
    assert success["properties"]["data"]["$ref"].endswith("/FleetStatus")
    assert terminal["properties"]["data"]["$ref"].endswith("/EmptyData")
    assert set(terminal["required"]) >= {"schema", "command", "data", "errors", "warnings"}


def test_schema_catalog_can_include_full_schemas() -> None:
    catalog = schema_catalog(include_schemas=True)
    output = next(item for item in catalog if item["name"] == "output-envelope")
    plan = next(item for item in catalog if item["name"] == "plan-envelope")

    assert output["title"] == "OutputEnvelope"
    assert output["schema"]["properties"]["command"]["type"] == "string"
    assert plan["commands"] == ["plan"]
    assert "oneOf" in plan["schema"]


def test_schema_catalog_entries_are_typed() -> None:
    catalog = schema_catalog(include_schemas=True)

    parsed = ApiSchemasResult.model_validate({"schemas": catalog})
    entry = next(item for item in parsed.schemas if item.name == "plan-envelope")

    assert entry.commands == ["plan"]
    assert entry.json_schema is not None
    assert next(item for item in catalog if item["name"] == "plan-envelope")["schema"] == entry.json_schema


def test_command_catalog_maps_commands_to_envelope_and_data_schemas() -> None:
    catalog = command_catalog()
    by_command = {item["command"]: item for item in catalog}

    assert by_command["plan"]["envelope_schema"] == "plan-envelope"
    assert by_command["plan"]["data_schema"] == "plan-result"
    assert by_command["plan"]["failure_data_schema"] == "empty-data"
    assert by_command["plan"]["error_schema"] == "error"
    assert by_command["plan"]["machine_flags"] == ["--json"]
    assert by_command["plan"]["argv"] == ["plan"]
    assert "changed" in by_command["plan"]["statuses"]
    assert {"status": "changed", "exit_code": 2, "category": "none", "meaning": "changes pending"} in by_command[
        "plan"
    ]["outcomes"]
    assert {
        "status": "failed",
        "exit_code": 2,
        "category": "user",
        "meaning": "user or configuration error",
    } in by_command["plan"]["outcomes"]
    assert by_command["client.list"]["data_schema"] == "client-list"
    assert by_command["api.commands"]["data_schema"] == "api-commands"
    assert by_command["fleet.status"]["data_schema"] == "fleet-status"
    assert by_command["fleet.inventory"]["statuses"] == ["ok", "failed", "cancelled"]
    assert by_command["fleet.inventory"]["exit_codes"]["130"] == "cancelled by the user"


def test_command_catalog_can_embed_command_schemas() -> None:
    catalog = command_catalog(include_schemas=True)
    plan = next(item for item in catalog if item["command"] == "plan")
    parsed = ApiCommandsResult.model_validate({"commands": catalog})

    success_ref = next(
        option["$ref"] for option in plan["envelope"]["oneOf"] if option["$ref"].endswith("/_PlanSuccessEnvelope")
    )
    success = plan["envelope"]["$defs"][success_ref.rsplit("/", 1)[-1]]
    assert success["properties"]["command"]["const"] == "plan"
    assert plan["data"]["title"] == "PlanResult"
    assert plan["failure_data"]["title"] == "EmptyData"
    assert plan["error"]["title"] == "MeridianError"
    assert next(item for item in parsed.commands if item.command == "plan").data is not None


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

    assert parsed.root.command == "plan"
    assert parsed.root.status == "failed"
    assert parsed.root.data.model_dump() == {}


def test_command_envelope_producer_validates_migrated_commands() -> None:
    with pytest.raises(ValidationError):
        command_envelope(
            command="plan",
            summary="Plan has changes",
            status="changed",
            exit_code=2,
            timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
        )


def test_command_envelope_producer_rejects_unsupported_success_exit_code() -> None:
    with pytest.raises(ValueError, match="unsupported outcome"):
        command_envelope(
            command="client.list",
            data=build_client_list_result([]).to_data(),
            summary="0 clients",
            status="ok",
            exit_code=2,
            timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
        )


def test_command_envelope_producer_rejects_unsupported_failure_exit_code() -> None:
    error = MeridianError(
        code="MERIDIAN_USER_ERROR",
        category="user",
        message="User error",
        exit_code=2,
    )

    with pytest.raises(ValueError, match="unsupported outcome"):
        command_envelope(
            command="client.list",
            summary="User error",
            status="failed",
            exit_code=0,
            errors=[error],
            timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
        )


def test_command_envelope_schema_rejects_failed_output_without_error() -> None:
    payload = envelope(
        command="plan",
        summary="No desired state defined in cluster.yml",
        status="failed",
        exit_code=2,
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )

    with pytest.raises(ValidationError):
        PlanOutputEnvelope.model_validate(payload.model_dump(mode="json", by_alias=True))


def test_command_envelope_schema_rejects_success_without_typed_data() -> None:
    payload = envelope(
        command="plan",
        summary="Plan has changes",
        status="changed",
        exit_code=2,
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )

    with pytest.raises(ValidationError):
        PlanOutputEnvelope.model_validate(payload.model_dump(mode="json", by_alias=True))


def test_unknown_schema_name_is_actionable() -> None:
    with pytest.raises(ValueError, match="Available:"):
        schema_for("missing")
