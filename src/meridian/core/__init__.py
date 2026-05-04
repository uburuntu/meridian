"""Meridian core API primitives.

Core modules expose typed request/result/event contracts used by CLI, future
UI clients, and automation adapters. They must not depend on Typer command
parsing or Rich console state.
"""

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
from meridian.core.output import EventStream, emit_json, emit_jsonl, envelope, plan_payload
from meridian.core.redaction import REDACTED, redact

__all__ = [
    "EventStream",
    "CoreModel",
    "ErrorCategory",
    "Event",
    "EventLevel",
    "MeridianError",
    "OutputEnvelope",
    "OutputStatus",
    "REDACTED",
    "ResourceRef",
    "Summary",
    "emit_json",
    "emit_jsonl",
    "envelope",
    "plan_payload",
    "redact",
]
