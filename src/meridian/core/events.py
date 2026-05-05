"""Shared event names for meridian-core progress streams."""

from __future__ import annotations

from typing import Final, Literal

CoreEventType = Literal[
    "command.started",
    "command.completed",
    "command.failed",
    "provision.step.started",
    "provision.step.completed",
    "provision.step.failed",
]

COMMAND_STARTED: Final[CoreEventType] = "command.started"
COMMAND_COMPLETED: Final[CoreEventType] = "command.completed"
COMMAND_FAILED: Final[CoreEventType] = "command.failed"

PROVISION_STEP_STARTED: Final[CoreEventType] = "provision.step.started"
PROVISION_STEP_COMPLETED: Final[CoreEventType] = "provision.step.completed"
PROVISION_STEP_FAILED: Final[CoreEventType] = "provision.step.failed"
