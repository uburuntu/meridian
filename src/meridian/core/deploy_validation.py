"""Deploy request validation helpers owned by meridian-core."""

from __future__ import annotations

import ipaddress
import re

from meridian.core.deploy import DeployRequest

_CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_LOCAL_TARGETS = {"local", "locally"}


class DeployValidationError(ValueError):
    """Raised when a deploy request is not executable."""

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def is_local_deploy_target(value: str) -> bool:
    """Return True for deploy targets that mean the current machine."""
    return value.lower() in _LOCAL_TARGETS


def is_ip_deploy_target(value: str) -> bool:
    """Return True when a deploy target is a valid IP address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def normalize_client_name(client_name: str) -> str:
    """Validate and default the first deploy client name."""
    if not client_name:
        return "default"
    if not _CLIENT_NAME_RE.match(client_name):
        raise DeployValidationError(
            f"Client name '{client_name}' is invalid",
            hint="Use letters, numbers, hyphens, and underscores.",
        )
    return client_name


def validate_deploy_target(target: str) -> None:
    """Validate a concrete deploy target after registry resolution."""
    if not target:
        raise DeployValidationError(
            "Deploy target is required",
            hint="Enter a server IP address or use --server with a registered server.",
        )
    if not is_local_deploy_target(target) and not is_ip_deploy_target(target):
        raise DeployValidationError(
            f"Invalid IP address: {target}",
            hint="Enter a valid IP address (e.g. meridian deploy 198.51.100.10).",
        )


def normalize_deploy_request(request: DeployRequest) -> DeployRequest:
    """Validate request-level deploy invariants and return a normalized copy."""
    if request.ip and request.requested_server:
        raise DeployValidationError(
            "Use either the IP address or --server, not both.",
            hint="Example: meridian deploy 198.51.100.10 OR meridian deploy --server mybox",
        )
    if not request.ip and not request.requested_server:
        raise DeployValidationError(
            "Deploy target is required",
            hint="Enter a server IP address or run the interactive wizard.",
        )
    if request.ip:
        validate_deploy_target(request.ip)
    return request.model_copy(update={"client_name": normalize_client_name(request.client_name)})
