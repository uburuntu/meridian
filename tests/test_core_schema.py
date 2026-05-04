"""Tests for meridian-core JSON Schema catalog."""

from __future__ import annotations

import pytest

from meridian.core.schema import schema_catalog, schema_for, schema_names


def test_schema_catalog_lists_public_contracts() -> None:
    names = schema_names()

    assert "output-envelope" in names
    assert "event" in names
    assert "plan-result" in names
    assert "fleet-status" in names
    assert "fleet-inventory" in names


def test_schema_for_output_envelope_uses_wire_aliases() -> None:
    schema = schema_for("output-envelope")

    assert "schema" in schema["properties"]
    assert "schema_version" not in schema["properties"]
    assert schema["properties"]["status"]["enum"] == ["ok", "changed", "no_changes", "failed", "cancelled"]


def test_schema_catalog_can_include_full_schemas() -> None:
    catalog = schema_catalog(include_schemas=True)
    output = next(item for item in catalog if item["name"] == "output-envelope")

    assert output["title"] == "OutputEnvelope"
    assert output["schema"]["properties"]["command"]["type"] == "string"


def test_unknown_schema_name_is_actionable() -> None:
    with pytest.raises(ValueError, match="Available:"):
        schema_for("missing")
