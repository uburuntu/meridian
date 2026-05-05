"""Tests for core deploy validation helpers."""

from __future__ import annotations

import pytest

from meridian.core.deploy import DeployRequest
from meridian.core.deploy_validation import (
    DeployValidationError,
    normalize_client_name,
    normalize_deploy_request,
    validate_deploy_target,
)


def test_normalize_client_name_defaults_empty_to_default() -> None:
    assert normalize_client_name("") == "default"


def test_normalize_client_name_rejects_invalid_value() -> None:
    with pytest.raises(DeployValidationError, match="invalid"):
        normalize_client_name("bad name!")


def test_validate_deploy_target_accepts_ip_and_local() -> None:
    validate_deploy_target("198.51.100.10")
    validate_deploy_target("local")


def test_validate_deploy_target_rejects_bad_target() -> None:
    with pytest.raises(DeployValidationError, match="Invalid IP address"):
        validate_deploy_target("not-an-ip")


def test_normalize_deploy_request_rejects_ip_and_server_together() -> None:
    with pytest.raises(DeployValidationError, match="either the IP address or --server"):
        normalize_deploy_request(DeployRequest(ip="198.51.100.10", requested_server="edge"))


def test_normalize_deploy_request_defaults_client_name() -> None:
    request = normalize_deploy_request(DeployRequest(ip="198.51.100.10"))

    assert request.client_name == "default"
