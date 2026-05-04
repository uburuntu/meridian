"""Tests for meridian-core output contracts."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from pydantic import ValidationError

from meridian.core.models import MeridianError, OutputEnvelope, ResourceRef, Summary
from meridian.core.output import EventStream, OperationTimer, emit_json, emit_jsonl, envelope
from meridian.core.redaction import REDACTED, redact


def test_output_envelope_has_stable_top_level_contract() -> None:
    timer = OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test")
    payload = envelope(
        command="fleet.inventory",
        data={"nodes": []},
        summary=Summary(text="0 nodes", changed=False, counts={"nodes": 0}),
        timer=timer,
    )

    stream = StringIO()
    emit_json(payload, stream=stream)
    data = json.loads(stream.getvalue())

    assert data["schema"] == "meridian.output/v1"
    assert data["command"] == "fleet.inventory"
    assert data["operation_id"] == "op-test"
    assert data["started_at"] == "2026-05-04T21:00:00Z"
    assert data["status"] == "ok"
    assert data["exit_code"] == 0
    assert data["summary"] == {"changed": False, "counts": {"nodes": 0}, "text": "0 nodes"}
    assert data["data"] == {"nodes": []}
    assert data["warnings"] == []
    assert data["errors"] == []


def test_output_envelope_serializes_errors() -> None:
    err = MeridianError(
        code="MERIDIAN_INPUT_REQUIRED",
        category="user",
        message="Missing server IP",
        hint="Pass --server-ip.",
        exit_code=2,
    )
    payload = envelope(
        command="deploy",
        summary="Missing input",
        status="failed",
        exit_code=2,
        errors=[err],
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )

    stream = StringIO()
    emit_json(payload, stream=stream)
    data = json.loads(stream.getvalue())

    assert data["status"] == "failed"
    assert data["errors"][0]["code"] == "MERIDIAN_INPUT_REQUIRED"
    assert data["errors"][0]["category"] == "user"
    assert data["errors"][0]["hint"] == "Pass --server-ip."


def test_output_envelope_is_validated_and_schema_exportable() -> None:
    payload = envelope(
        command="plan",
        summary="Plan has changes",
        status="changed",
        timer=OperationTimer(started_at="2026-05-04T21:00:00Z", operation_id="op-test"),
    )
    schema = OutputEnvelope.model_json_schema()

    assert "schema" in schema["properties"]
    assert schema["properties"]["status"]["enum"] == ["ok", "changed", "no_changes", "failed", "cancelled"]
    with pytest.raises(ValidationError):
        OutputEnvelope.model_validate({**payload.model_dump(), "status": "surprising"})


def test_emit_json_redacts_sensitive_keys_and_text() -> None:
    stream = StringIO()
    emit_json(
        {
            "api_token": "secret-token",
            "message": "password=hunter2 jwt=eyJaaaaaaaa.eyJbbbbbbbb.eyJcccccccc",
            "nested": {"database_url": "postgres://user:pass@example/db"},
        },
        stream=stream,
    )
    data = json.loads(stream.getvalue())

    assert data["api_token"] == REDACTED
    assert "hunter2" not in data["message"]
    assert "eyJaaaaaaaa" not in data["message"]
    assert data["nested"]["database_url"] == REDACTED


def test_redact_string_handles_url_userinfo() -> None:
    assert redact("postgres://user:pass@example.org/db") == f"postgres://{REDACTED}@example.org/db"


def test_jsonl_events_are_monotonic_and_redacted() -> None:
    stream = StringIO()
    events = EventStream(operation_id="op-test", stream=stream)

    first = events.emit(
        "provision.step.started",
        phase="provision",
        resource=ResourceRef(kind="node", id="198.51.100.1", name="exit-a"),
        message="Install Docker",
    )
    second = events.emit(
        "ssh.command.completed",
        phase="ssh",
        data={"command": "curl -H 'Authorization: Bearer eyJaaaaaaaa.eyJbbbbbbbb.eyJcccccccc'"},
    )

    assert first.seq == 1
    assert second.seq == 2
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert lines[0]["schema"] == "meridian.event/v1"
    assert lines[0]["operation_id"] == "op-test"
    assert lines[0]["seq"] == 1
    assert lines[1]["seq"] == 2
    assert "eyJaaaaaaaa" not in lines[1]["data"]["command"]


def test_emit_jsonl_writes_one_compact_record() -> None:
    stream = StringIO()
    emit_jsonl({"b": 2, "a": 1}, stream=stream)
    assert stream.getvalue() == '{"a":1,"b":2}\n'
