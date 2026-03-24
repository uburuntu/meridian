"""Tests for build_setup_steps() pipeline assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.provision import build_setup_steps
from meridian.provision.steps import ProvisionContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def step_names(ctx: ProvisionContext) -> list[str]:
    """Return the list of step names for a given context."""
    return [s.name for s in build_setup_steps(ctx)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_ctx(tmp_path: Path) -> ProvisionContext:
    """Minimal context: no domain, no hosted page, harden off, xhttp off."""
    return ProvisionContext(
        ip="198.51.100.1",
        harden=False,
        xhttp_enabled=False,
        hosted_page=False,
        domain="",
        creds_dir=str(tmp_path / "creds"),
    )


@pytest.fixture
def domain_ctx(tmp_path: Path) -> ProvisionContext:
    """Context with domain mode enabled and all features on."""
    return ProvisionContext(
        ip="198.51.100.1",
        domain="example.com",
        harden=True,
        xhttp_enabled=True,
        hosted_page=False,
        creds_dir=str(tmp_path / "creds"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMinimalPipeline:
    def test_minimal_step_count(self, base_ctx: ProvisionContext):
        """Minimal config: disk check, packages, auto-upgrades, timezone, BBR, docker,
        deploy 3xui, configure panel, login, reality, verify xray = 11 steps."""
        steps = build_setup_steps(base_ctx)
        names = [s.name for s in steps]
        assert len(steps) == 11, f"Expected 11 minimal steps, got {len(steps)}: {names}"

    def test_no_services_without_domain_or_hosted_page(self, base_ctx: ProvisionContext):
        names = step_names(base_ctx)
        assert "Install HAProxy" not in names
        assert "Install Caddy" not in names
        assert "Deploy connection page" not in names


class TestHardenSteps:
    def test_harden_adds_two_steps(self, base_ctx: ProvisionContext):
        names_without = step_names(base_ctx)
        base_ctx.harden = True
        names_with = step_names(base_ctx)
        added = set(names_with) - set(names_without)
        assert "Harden SSH configuration" in added
        assert "Configure firewall" in added
        assert len(names_with) == len(names_without) + 2


class TestXHTTPStep:
    def test_xhttp_enabled_adds_step(self, base_ctx: ProvisionContext):
        names_without = step_names(base_ctx)
        base_ctx.xhttp_enabled = True
        names_with = step_names(base_ctx)
        added = set(names_with) - set(names_without)
        assert "Create XHTTP inbound" in added


class TestDomainMode:
    def test_domain_mode_adds_wss_and_services(self, tmp_path: Path):
        ctx = ProvisionContext(
            ip="198.51.100.1",
            domain="example.com",
            harden=False,
            xhttp_enabled=False,
            hosted_page=False,
            creds_dir=str(tmp_path / "creds"),
        )
        names = step_names(ctx)
        assert "Create WSS inbound" in names
        assert "Install HAProxy" in names
        assert "Install Caddy" in names
        assert "Deploy PWA assets" in names
        assert "Deploy connection page" in names


class TestHostedPage:
    def test_hosted_page_adds_services(self, base_ctx: ProvisionContext):
        base_ctx.hosted_page = True
        names = step_names(base_ctx)
        assert "Install HAProxy" in names
        assert "Install Caddy" in names
        assert "Deploy PWA assets" in names
        assert "Deploy connection page" in names


class TestFullPipeline:
    def test_full_pipeline_step_count(self, domain_ctx: ProvisionContext):
        """All flags on: disk check + common(3) + harden(2) + BBR + docker(2) + panel(2)
        + reality + xhttp + wss + verify + haproxy + caddy + pwa assets + connection page = 19."""
        steps = build_setup_steps(domain_ctx)
        names = [s.name for s in steps]
        assert len(steps) == 19, f"Expected 19 full steps, got {len(steps)}: {names}"


class TestStepOrdering:
    def test_step_ordering(self, domain_ctx: ProvisionContext):
        names = step_names(domain_ctx)

        def assert_before(a: str, b: str) -> None:
            assert a in names, f"{a!r} not found in steps"
            assert b in names, f"{b!r} not found in steps"
            assert names.index(a) < names.index(b), f"{a!r} should come before {b!r}, got order: {names}"

        # Packages before Docker
        assert_before("Install system packages", "Install Docker")
        # Docker before panel
        assert_before("Install Docker", "Deploy 3x-ui panel")
        assert_before("Deploy 3x-ui panel", "Configure panel")
        # Panel before inbounds
        assert_before("Log in to panel", "Create Reality inbound")
        # Inbounds before verify
        assert_before("Create Reality inbound", "Verify Xray configuration")
        # Verify before services
        assert_before("Verify Xray configuration", "Install HAProxy")
        assert_before("Install HAProxy", "Install Caddy")
        assert_before("Install Caddy", "Deploy PWA assets")
        assert_before("Deploy PWA assets", "Deploy connection page")
