"""Tests for build_setup_steps() pipeline assembly.

4.0: Updated for Remnawave panel/node architecture (replaces 3x-ui).
"""

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
        """Minimal config: disk check, packages, auto-upgrades, timezone, BBR,
        ensure port 443, docker, remnawave panel = 8 steps (no nginx without hosted_page)."""
        steps = build_setup_steps(base_ctx)
        names = [s.name for s in steps]
        assert len(steps) == 8, f"Expected 8 minimal steps, got {len(steps)}: {names}"

    def test_no_services_without_domain_or_hosted_page(self, base_ctx: ProvisionContext):
        names = step_names(base_ctx)
        assert "Install nginx" not in names
        assert "Configure nginx" not in names
        assert "Issue TLS certificate" not in names
        assert "Deploy connection page" not in names


class TestHardenSteps:
    def test_harden_adds_ssh_and_firewall(self, base_ctx: ProvisionContext):
        names_without = step_names(base_ctx)
        base_ctx.harden = True
        names_with = step_names(base_ctx)
        # harden=True replaces EnsurePort443 with HardenSSH + ConfigureFail2ban + ConfigureFirewall (+2 net)
        assert "Harden SSH configuration" in names_with
        assert "Configure fail2ban" in names_with
        assert "Configure firewall" in names_with
        assert "Ensure port 443" not in names_with
        assert "Ensure port 443" in names_without
        assert len(names_with) == len(names_without) + 2


class TestHostedPage:
    def test_hosted_page_adds_services(self, base_ctx: ProvisionContext):
        base_ctx.hosted_page = True
        names = step_names(base_ctx)
        assert "Install nginx" in names
        assert "Configure nginx" in names
        assert "Issue TLS certificate" in names
        assert "Deploy PWA assets" in names


class TestDomainMode:
    def test_domain_mode_adds_services(self, tmp_path: Path):
        ctx = ProvisionContext(
            ip="198.51.100.1",
            domain="example.com",
            harden=False,
            xhttp_enabled=False,
            hosted_page=False,
            creds_dir=str(tmp_path / "creds"),
        )
        names = step_names(ctx)
        assert "Install nginx" in names
        assert "Configure nginx" in names
        assert "Issue TLS certificate" in names
        assert "Deploy PWA assets" in names


class TestFullPipeline:
    def test_full_pipeline_has_remnawave_steps(self, domain_ctx: ProvisionContext):
        """Verify the full pipeline includes Remnawave panel step."""
        names = step_names(domain_ctx)
        assert "Deploy Remnawave panel" in names
        assert "Install Docker" in names
        assert "Install nginx" in names
        assert "Issue TLS certificate" in names


class TestStepOrdering:
    def test_step_ordering(self, domain_ctx: ProvisionContext):
        names = step_names(domain_ctx)

        def assert_before(a: str, b: str) -> None:
            assert a in names, f"{a!r} not found in steps"
            assert b in names, f"{b!r} not found in steps"
            assert names.index(a) < names.index(b), f"{a!r} should come before {b!r}, got order: {names}"

        # Packages before Docker
        assert_before("Install system packages", "Install Docker")
        # Docker before Remnawave
        assert_before("Install Docker", "Deploy Remnawave panel")
        # Remnawave before nginx
        assert_before("Deploy Remnawave panel", "Install nginx")
        assert_before("Install nginx", "Configure nginx")
        assert_before("Configure nginx", "Issue TLS certificate")
        assert_before("Issue TLS certificate", "Deploy PWA assets")


class TestNodeOnlyPipeline:
    def test_node_only_no_panel(self, base_ctx: ProvisionContext):
        """When is_panel_host is False, panel step is skipped."""
        base_ctx.is_panel_host = False
        names = step_names(base_ctx)
        assert "Deploy Remnawave panel" not in names
