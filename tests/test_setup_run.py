"""Tests for run() entry point — mode detection, input validation, port computation.

Covers the deploy command's orchestration: first deploy vs redeploy vs blocked,
IP/flag validation, deterministic port computation, and path reuse.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import typer

from meridian.cluster import (
    ClusterConfig,
    InboundRef,
    NodeEntry,
    PanelConfig,
    ProtocolKey,
)
from meridian.commands.setup import run

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IP_A = "198.51.100.1"
_IP_B = "198.51.100.2"
_UUID_A = "550e8400-e29b-41d4-a716-446655440000"
_UUID_B = "660e8400-e29b-41d4-a716-446655440001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_cluster() -> ClusterConfig:
    return ClusterConfig()


def _configured_cluster(ip: str = _IP_A) -> ClusterConfig:
    return ClusterConfig(
        panel=PanelConfig(
            url=f"https://{ip}/panel",
            api_token="test-jwt-token",
            server_ip=ip,
            secret_path="existing_secret_path",
        ),
        nodes=[
            NodeEntry(
                ip=ip,
                uuid=_UUID_A,
                is_panel_host=True,
                xhttp_path="existing_xhttp_path",
                ws_path="existing_ws_path",
            ),
        ],
        inbounds={
            ProtocolKey.REALITY: InboundRef(uuid=_UUID_B, tag="vless-reality"),
        },
    )


def _make_resolved(ip: str = _IP_A) -> SimpleNamespace:
    conn = MagicMock()
    conn.port = 22
    return SimpleNamespace(ip=ip, user="root", conn=conn, local_mode=False)


def _patch_all(**overrides: object):  # noqa: ANN202
    """Context manager that patches all external calls in run().

    Returns a dict of all mocks for assertion.
    """
    defaults = {
        "meridian.commands.setup.resolve_server": MagicMock(return_value=_make_resolved()),
        "meridian.commands.setup.ensure_server_connection": MagicMock(
            side_effect=lambda r: r
        ),
        "meridian.commands.setup._check_ports": MagicMock(),
        "meridian.commands.setup._run_provisioner": MagicMock(),
        "meridian.commands.setup._configure_panel_and_node": MagicMock(),
        "meridian.commands.setup._print_success": MagicMock(),
        "meridian.commands.setup._offer_relay": MagicMock(),
    }
    defaults.update(overrides)

    import contextlib

    return contextlib.ExitStack(), defaults


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


class TestRunModeDetection:
    def _run_with_cluster(self, cluster: ClusterConfig, ip: str = _IP_A) -> dict:
        """Execute run() with given cluster config, capturing calls."""
        resolved = _make_resolved(ip)
        mocks: dict[str, MagicMock] = {}
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner") as mock_prov,
            patch("meridian.commands.setup._configure_panel_and_node") as mock_config,
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            mocks["_run_provisioner"] = mock_prov
            mocks["_configure_panel_and_node"] = mock_config
            run(ip=ip, yes=True)
        return mocks

    def test_empty_cluster_triggers_first_deploy(self) -> None:
        mocks = self._run_with_cluster(_empty_cluster())
        call_kwargs = mocks["_configure_panel_and_node"].call_args
        assert call_kwargs.kwargs["is_first_deploy"] is True
        assert call_kwargs.kwargs["is_redeploy"] is False

    def test_existing_node_ip_triggers_redeploy(self) -> None:
        mocks = self._run_with_cluster(_configured_cluster(_IP_A), ip=_IP_A)
        call_kwargs = mocks["_configure_panel_and_node"].call_args
        assert call_kwargs.kwargs["is_first_deploy"] is False
        assert call_kwargs.kwargs["is_redeploy"] is True

    def test_new_ip_on_configured_cluster_fails_with_node_add_hint(self) -> None:
        cluster = _configured_cluster(_IP_A)
        resolved = _make_resolved(_IP_B)
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            pytest.raises(typer.Exit) as exc_info,
        ):
            run(ip=_IP_B, yes=True)
        assert exc_info.value.exit_code != 0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestRunInputValidation:
    def test_invalid_ip_exits(self) -> None:
        with pytest.raises(typer.Exit):
            run(ip="not-an-ip", yes=True)

    def test_both_ip_and_server_flag_fails(self) -> None:
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            pytest.raises(typer.Exit),
        ):
            run(ip=_IP_A, requested_server="mybox", yes=True)

    def test_invalid_client_name_exits(self) -> None:
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            pytest.raises(typer.Exit),
        ):
            run(ip=_IP_A, client_name="invalid--!name", yes=True)

    def test_empty_client_name_defaults_to_default(self) -> None:
        cluster = _empty_cluster()
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner"),
            patch("meridian.commands.setup._configure_panel_and_node") as mock_config,
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, client_name="", yes=True)
        assert mock_config.call_args.kwargs["client_name"] == "default"

    def test_valid_client_name_passes_through(self) -> None:
        cluster = _empty_cluster()
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner"),
            patch("meridian.commands.setup._configure_panel_and_node") as mock_config,
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, client_name="alice", yes=True)
        assert mock_config.call_args.kwargs["client_name"] == "alice"


# ---------------------------------------------------------------------------
# Port computation
# ---------------------------------------------------------------------------


class TestRunPortComputation:
    def _get_ports(self, ip: str) -> dict:
        """Run deploy and capture the port values passed to provisioner."""
        cluster = _empty_cluster()
        resolved = _make_resolved(ip)
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner") as mock_prov,
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=ip, yes=True)
        return {
            "xhttp_port": mock_prov.call_args.kwargs["xhttp_port"],
            "reality_port": mock_prov.call_args.kwargs["reality_port"],
            "wss_port": mock_prov.call_args.kwargs["wss_port"],
        }

    def test_ports_deterministic_from_ip(self) -> None:
        ports1 = self._get_ports(_IP_A)
        ports2 = self._get_ports(_IP_A)
        assert ports1 == ports2

    def test_different_ips_produce_different_ports(self) -> None:
        ports_a = self._get_ports(_IP_A)
        ports_b = self._get_ports(_IP_B)
        # At least one port differs
        assert ports_a != ports_b

    def test_xhttp_port_in_range(self) -> None:
        ports = self._get_ports(_IP_A)
        assert 30000 <= ports["xhttp_port"] < 40000

    def test_reality_port_in_range(self) -> None:
        ports = self._get_ports(_IP_A)
        assert 10000 <= ports["reality_port"] < 11000

    def test_wss_port_in_range(self) -> None:
        ports = self._get_ports(_IP_A)
        assert 20000 <= ports["wss_port"] < 30000

    def test_ports_match_hash_formula(self) -> None:
        ip_hash = int(hashlib.sha256(_IP_A.encode()).hexdigest()[:8], 16)
        ports = self._get_ports(_IP_A)
        assert ports["xhttp_port"] == 30000 + (ip_hash % 10000)
        assert ports["reality_port"] == 10000 + ip_hash % 1000
        assert ports["wss_port"] == 20000 + (ip_hash % 10000)


# ---------------------------------------------------------------------------
# Secret path reuse
# ---------------------------------------------------------------------------


class TestRunSecretPathReuse:
    def test_first_deploy_generates_new_secret_path(self) -> None:
        cluster = _empty_cluster()
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner") as mock_prov,
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, yes=True)
        secret_path = mock_prov.call_args.kwargs["secret_path"]
        assert len(secret_path) == 24  # secrets.token_hex(12) → 24 chars
        assert secret_path != ""

    def test_redeploy_reuses_existing_secret_path(self) -> None:
        cluster = _configured_cluster(_IP_A)
        resolved = _make_resolved(_IP_A)
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner") as mock_prov,
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, yes=True)
        assert mock_prov.call_args.kwargs["secret_path"] == "existing_secret_path"


# ---------------------------------------------------------------------------
# XHTTP/WS path reuse
# ---------------------------------------------------------------------------


class TestRunPathReuse:
    def test_first_deploy_generates_new_xhttp_path(self) -> None:
        cluster = _empty_cluster()
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner") as mock_prov,
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, yes=True)
        xhttp_path = mock_prov.call_args.kwargs["xhttp_path"]
        ws_path = mock_prov.call_args.kwargs["ws_path"]
        assert len(xhttp_path) == 16  # secrets.token_hex(8)
        assert len(ws_path) == 16

    def test_redeploy_reuses_existing_paths(self) -> None:
        cluster = _configured_cluster(_IP_A)
        resolved = _make_resolved(_IP_A)
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner") as mock_prov,
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, yes=True)
        assert mock_prov.call_args.kwargs["xhttp_path"] == "existing_xhttp_path"
        assert mock_prov.call_args.kwargs["ws_path"] == "existing_ws_path"


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------


class TestRunBranding:
    def test_branding_saved_when_provided(self) -> None:
        cluster = _empty_cluster()
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner"),
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, yes=True, server_name="My VPN", icon="shield", color="ocean")
        assert cluster.branding is not None
        assert cluster.branding.server_name == "My VPN"
        assert cluster.branding.icon == "shield"
        assert cluster.branding.color == "ocean"

    def test_branding_not_overwritten_when_all_empty(self) -> None:
        """When no branding flags given, existing branding stays unchanged."""
        cluster = _empty_cluster()
        original_branding = cluster.branding
        resolved = _make_resolved()
        with (
            patch("meridian.commands.setup.ServerRegistry"),
            patch("meridian.commands.setup.resolve_server", return_value=resolved),
            patch("meridian.commands.setup.ensure_server_connection", side_effect=lambda r: r),
            patch("meridian.commands.setup._check_ports"),
            patch("meridian.commands.setup.ClusterConfig.load", return_value=cluster),
            patch("meridian.commands.setup._run_provisioner"),
            patch("meridian.commands.setup._configure_panel_and_node"),
            patch("meridian.commands.setup.ClusterConfig.save"),
            patch("meridian.commands.setup._print_success"),
            patch("meridian.commands.setup._offer_relay"),
            patch("meridian.commands.setup._build_redeploy_command", return_value=""),
        ):
            run(ip=_IP_A, yes=True)
        # Branding should not be replaced with new values
        assert cluster.branding is original_branding
