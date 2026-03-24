"""Tests for relay node provisioning steps."""

from __future__ import annotations

import pytest

from meridian.config import REALM_SHA256, REALM_VERSION
from meridian.provision.relay import (
    ConfigureRealm,
    ConfigureRelayBBR,
    InstallRealm,
    InstallRelayPackages,
    RelayContext,
    VerifyRelay,
    build_relay_steps,
)
from tests.provision.conftest import MockConnection

# ---------------------------------------------------------------------------
# RelayContext validation
# ---------------------------------------------------------------------------


class TestRelayContextValidation:
    def test_valid_ips_accepted(self):
        ctx = RelayContext(relay_ip="198.51.100.10", exit_ip="198.51.100.1")
        assert ctx.relay_ip == "198.51.100.10"
        assert ctx.exit_ip == "198.51.100.1"

    def test_invalid_relay_ip_raises(self):
        with pytest.raises(ValueError, match="Invalid IP address for relay_ip"):
            RelayContext(relay_ip="not-an-ip", exit_ip="198.51.100.1")

    def test_invalid_port_raises(self):
        with pytest.raises(ValueError, match="Invalid port for listen_port"):
            RelayContext(
                relay_ip="198.51.100.10",
                exit_ip="198.51.100.1",
                listen_port=0,
            )

    def test_port_too_high_raises(self):
        with pytest.raises(ValueError, match="Invalid port for listen_port"):
            RelayContext(
                relay_ip="198.51.100.10",
                exit_ip="198.51.100.1",
                listen_port=70000,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides: object) -> RelayContext:
    """Build a RelayContext with RFC 5737 test IPs."""
    defaults = dict(relay_ip="198.51.100.10", exit_ip="198.51.100.1")
    defaults.update(overrides)
    return RelayContext(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# InstallRelayPackages
# ---------------------------------------------------------------------------


class TestInstallRelayPackages:
    def test_all_present(self):
        conn = MockConnection()
        conn.when("dpkg-query", stdout="curl\nwget\nufw\nca-certificates\n")
        result = InstallRelayPackages().run(conn, _make_ctx())
        assert result.status == "ok"

    def test_missing_triggers_install(self):
        conn = MockConnection()
        # dpkg-query returns only a subset
        conn.when("dpkg-query", stdout="curl\nwget\n")
        conn.when("apt-get update", stdout="")
        conn.when("apt-get install", stdout="")
        result = InstallRelayPackages().run(conn, _make_ctx())
        assert result.status == "changed"
        conn.assert_called_with_pattern("apt-get install")


# ---------------------------------------------------------------------------
# ConfigureRelayBBR
# ---------------------------------------------------------------------------


class TestConfigureRelayBBR:
    def test_already_enabled(self):
        conn = MockConnection()
        conn.when("tcp_congestion_control", stdout="bbr")
        conn.when("default_qdisc", stdout="fq")
        result = ConfigureRelayBBR().run(conn, _make_ctx())
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# InstallRealm
# ---------------------------------------------------------------------------


class TestInstallRealm:
    def test_correct_version_already_installed(self):
        conn = MockConnection()
        conn.when("realm --version", stdout=f"realm {REALM_VERSION}")
        result = InstallRealm().run(conn, _make_ctx())
        assert result.status == "ok"
        assert REALM_VERSION in result.detail

    def test_downloads_when_missing(self):
        conn = MockConnection()
        # Initial check includes "2>/dev/null"; verify after install does not.
        # First-match: the specific pattern wins for the initial probe.
        conn.when("realm --version 2>/dev/null", rc=1, stderr="command not found")
        conn.when("realm --version", stdout=f"realm {REALM_VERSION}")
        conn.when("uname -m", stdout="x86_64")
        conn.when("curl", stdout="")
        conn.when("sha256sum", stdout=REALM_SHA256["x86_64-unknown-linux-gnu"])
        conn.when("tar xzf", stdout="")
        result = InstallRealm().run(conn, _make_ctx())
        assert result.status == "changed"
        conn.assert_called_with_pattern("curl")


# ---------------------------------------------------------------------------
# ConfigureRealm
# ---------------------------------------------------------------------------


class TestConfigureRealm:
    def test_writes_config_and_restarts(self):
        conn = MockConnection()
        ctx = _make_ctx()
        result = ConfigureRealm().run(conn, ctx)
        assert result.status == "changed"
        # Verify realm.toml content was written
        conn.assert_called_with_pattern("realm.toml")
        # Verify systemctl restart was called
        conn.assert_called_with_pattern("systemctl restart")
        # Verify the exit IP appears in a call (config content)
        conn.assert_called_with_pattern(ctx.exit_ip)


# ---------------------------------------------------------------------------
# VerifyRelay
# ---------------------------------------------------------------------------


class TestVerifyRelay:
    def test_service_active_exit_reachable(self):
        conn = MockConnection()
        conn.when("systemctl is-active", stdout="active")
        conn.when("nc -z", stdout="")
        result = VerifyRelay().run(conn, _make_ctx())
        assert result.status == "ok"
        assert "exit reachable" in result.detail

    def test_localhost_fallback(self):
        """When nc to exit fails, fallback to localhost succeeds."""
        conn = MockConnection()
        conn.when("systemctl is-active", stdout="active")
        # nc to exit IP fails, but nc to 127.0.0.1 succeeds
        conn.when("nc -z -w 5 198.51.100.1", rc=1)
        conn.when("nc -z -w 3 127.0.0.1", stdout="")
        result = VerifyRelay().run(conn, _make_ctx())
        assert result.status == "ok"
        assert "relay port" in result.detail

    def test_service_not_active_fails(self):
        conn = MockConnection()
        conn.when("systemctl is-active", stdout="inactive", rc=1)
        conn.when("journalctl", stdout="some error log")
        result = VerifyRelay().run(conn, _make_ctx())
        assert result.status == "failed"


# ---------------------------------------------------------------------------
# build_relay_steps
# ---------------------------------------------------------------------------


class TestBuildRelaySteps:
    def test_returns_six_steps(self):
        ctx = _make_ctx()
        steps = build_relay_steps(ctx)
        assert len(steps) == 6
