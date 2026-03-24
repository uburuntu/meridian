"""Tests for HAProxy, Caddy, and connection page provisioning steps."""

from __future__ import annotations

from pathlib import Path

from meridian.provision.services import (
    DeployConnectionPage,
    DeployPWAAssets,
    InstallHAProxy,
    _render_caddy_config,
    _render_caddy_ip_config,
    _render_haproxy_cfg,
)
from meridian.provision.steps import ProvisionContext
from tests.provision.conftest import MockConnection, make_credentials

# ---------------------------------------------------------------------------
# Config rendering: HAProxy
# ---------------------------------------------------------------------------


class TestRenderHAProxyCfg:
    def test_contains_sni_routing(self):
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
        )
        assert "www.microsoft.com" in cfg
        assert "use_backend xray_reality" in cfg

    def test_no_check_on_backends(self):
        """HAProxy convention: no 'check' keyword on TLS backend server lines."""
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
        )
        # Extract only the 'server' lines in backend sections
        for line in cfg.splitlines():
            stripped = line.strip()
            if stripped.startswith("server "):
                assert "check" not in stripped, f"Backend server line must NOT use 'check': {stripped}"


# ---------------------------------------------------------------------------
# Config rendering: Caddy IP mode
# ---------------------------------------------------------------------------


class TestRenderCaddyIpConfig:
    def test_has_acme_shortlived(self):
        cfg = _render_caddy_ip_config(
            server_ip="198.51.100.1",
            caddy_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "profile shortlived" in cfg


# ---------------------------------------------------------------------------
# InstallHAProxy step
# ---------------------------------------------------------------------------


class TestInstallHAProxy:
    def test_already_installed_writes_config(self, tmp_path: Path):
        conn = MockConnection()
        # dpkg shows haproxy installed
        conn.when("dpkg -l haproxy", stdout="ii  haproxy")
        # config write + validation + reload all succeed
        conn.when("printf", stdout="")
        conn.when("haproxy -c", stdout="Configuration file is valid")
        conn.when("systemctl", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path))
        step = InstallHAProxy(reality_sni="www.microsoft.com")
        result = step.run(conn, ctx)
        # Already installed -> "ok" (not "changed")
        assert result.status == "ok"

    def test_validates_config(self, tmp_path: Path):
        conn = MockConnection()
        conn.when("dpkg -l haproxy", stdout="ii  haproxy")
        conn.when("printf", stdout="")
        conn.when("haproxy -c", stdout="")
        conn.when("systemctl", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path))
        step = InstallHAProxy(reality_sni="www.microsoft.com")
        step.run(conn, ctx)
        conn.assert_called_with_pattern("haproxy -c")


# ---------------------------------------------------------------------------
# DeployConnectionPage step
# ---------------------------------------------------------------------------


class TestDeployConnectionPage:
    def test_no_credentials_fails(self, tmp_path: Path):
        conn = MockConnection()
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path))
        # Provide credentials with empty reality UUID to trigger failure
        creds = make_credentials()
        creds.protocols["reality"].uuid = ""
        ctx["credentials"] = creds

        step = DeployConnectionPage(server_ip="198.51.100.1")
        result = step.run(conn, ctx)
        assert result.status == "failed"
        assert "UUID" in result.detail


# ---------------------------------------------------------------------------
# DeployPWAAssets step
# ---------------------------------------------------------------------------


class TestDeployPWAAssets:
    def test_uploads_static_files(self, tmp_path: Path):
        conn = MockConnection()
        conn.when("mkdir", stdout="")
        conn.when("printf", stdout="")
        conn.when("chown", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path))
        step = DeployPWAAssets()
        result = step.run(conn, ctx)
        assert result.status == "changed"
        assert "PWA" in result.detail

    def test_failure_returns_failed(self, tmp_path: Path):
        conn = MockConnection()
        conn.when("mkdir", stdout="")
        # File upload fails
        conn.when("printf", stdout="", rc=1)

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path))
        step = DeployPWAAssets()
        result = step.run(conn, ctx)
        assert result.status == "failed"


# ---------------------------------------------------------------------------
# Caddy config: PWA headers
# ---------------------------------------------------------------------------


class TestCaddyPWAHeaders:
    def _ip_config(self) -> str:
        return _render_caddy_ip_config(
            server_ip="198.51.100.1",
            caddy_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )

    def _domain_config(self) -> str:
        return _render_caddy_config(
            domain="example.com",
            caddy_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )

    def test_ip_config_has_manifest_content_type(self):
        cfg = self._ip_config()
        assert "application/manifest+json" in cfg

    def test_ip_config_has_service_worker_allowed(self):
        cfg = self._ip_config()
        assert "Service-Worker-Allowed" in cfg

    def test_ip_config_has_pwa_asset_cache(self):
        cfg = self._ip_config()
        assert "max-age=86400" in cfg

    def test_ip_config_has_dynamic_no_cache(self):
        cfg = self._ip_config()
        assert "no-cache, must-revalidate" in cfg

    def test_domain_config_has_manifest_content_type(self):
        cfg = self._domain_config()
        assert "application/manifest+json" in cfg

    def test_domain_config_has_service_worker_allowed(self):
        cfg = self._domain_config()
        assert "Service-Worker-Allowed" in cfg

    def test_domain_config_has_pwa_asset_cache(self):
        cfg = self._domain_config()
        assert "max-age=86400" in cfg
