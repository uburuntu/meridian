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
    _render_stats_script,
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
            server_ip="198.51.100.1",
        )
        assert "www.microsoft.com" in cfg
        assert "use_backend xray_reality" in cfg

    def test_no_check_on_backends(self):
        """HAProxy convention: no 'check' keyword on TLS backend server lines."""
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
            server_ip="198.51.100.1",
        )
        # Extract only the 'server' lines in backend sections
        for line in cfg.splitlines():
            stripped = line.strip()
            if stripped.startswith("server "):
                assert "check" not in stripped, f"Backend server line must NOT use 'check': {stripped}"

    def test_no_default_backend(self):
        """Unknown SNI must NOT be forwarded — no default_backend allowed."""
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "default_backend" not in cfg

    def test_server_ip_routes_to_caddy(self):
        """Server IP must be an explicit SNI routing to Caddy."""
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "use_backend caddy_https if { req_ssl_sni -i 198.51.100.1 }" in cfg

    def test_domain_routes_to_caddy(self):
        """In domain mode, the domain must also route to Caddy."""
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
            server_ip="198.51.100.1",
            domain="example.com",
        )
        assert "use_backend caddy_https if { req_ssl_sni -i example.com }" in cfg
        assert "use_backend caddy_https if { req_ssl_sni -i 198.51.100.1 }" in cfg

    def test_no_domain_no_domain_rule(self):
        """Without domain, only server IP should route to Caddy."""
        cfg = _render_haproxy_cfg(
            reality_sni="www.microsoft.com",
            haproxy_reality_backend_port=10443,
            caddy_internal_port=8443,
            server_ip="198.51.100.1",
        )
        # Only one caddy_https rule (for server IP)
        caddy_rules = [line for line in cfg.splitlines() if "use_backend caddy_https" in line]
        assert len(caddy_rules) == 1


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


# ---------------------------------------------------------------------------
# Caddy config: XHTTP block (Gap #2)
# ---------------------------------------------------------------------------


class TestCaddyXHTTPBlock:
    """Verify XHTTP reverse_proxy block in Caddy config renderers."""

    def test_ip_config_xhttp_reverse_proxy(self):
        cfg = _render_caddy_ip_config(
            server_ip="198.51.100.1",
            caddy_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-abc123",
            xhttp_internal_port=29000,
        )
        assert "reverse_proxy 127.0.0.1:29000" in cfg
        assert "flush_interval -1" in cfg
        assert "xh-abc123" in cfg

    def test_domain_config_xhttp_reverse_proxy(self):
        cfg = _render_caddy_config(
            domain="example.com",
            caddy_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-def456",
            xhttp_internal_port=29500,
        )
        assert "reverse_proxy 127.0.0.1:29500" in cfg
        assert "flush_interval -1" in cfg
        assert "xh-def456" in cfg

    def test_ip_config_xhttp_before_panel(self):
        """XHTTP handle block must appear BEFORE the panel handle block in Caddy config."""
        cfg = _render_caddy_ip_config(
            server_ip="198.51.100.1",
            caddy_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-test",
            xhttp_internal_port=29000,
        )
        xhttp_pos = cfg.index("xh-test")
        panel_pos = cfg.index("secretpanel")
        assert xhttp_pos < panel_pos, "XHTTP block must appear before panel block"

    def test_domain_config_xhttp_before_panel(self):
        """XHTTP handle block must appear BEFORE the panel handle block in domain config."""
        cfg = _render_caddy_config(
            domain="example.com",
            caddy_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-test2",
            xhttp_internal_port=29000,
        )
        xhttp_pos = cfg.index("xh-test2")
        panel_pos = cfg.index("secretpanel")
        assert xhttp_pos < panel_pos, "XHTTP block must appear before panel block"

    def test_ip_config_no_xhttp_without_params(self):
        """When xhttp_path is empty, no XHTTP block should be present."""
        cfg = _render_caddy_ip_config(
            server_ip="198.51.100.1",
            caddy_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "XHTTP" not in cfg

    def test_domain_config_no_xhttp_without_params(self):
        """When xhttp_path is empty, no XHTTP block should be present."""
        cfg = _render_caddy_config(
            domain="example.com",
            caddy_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "XHTTP" not in cfg

    def test_xhttp_has_read_timeout(self):
        """XHTTP transport should have read_timeout configured."""
        cfg = _render_caddy_ip_config(
            server_ip="198.51.100.1",
            caddy_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-test",
            xhttp_internal_port=29000,
        )
        assert "read_timeout 360s" in cfg


# ---------------------------------------------------------------------------
# Caddy handle_path structural validation (Gap #3)
# ---------------------------------------------------------------------------


class TestCaddyHandlePathStructure:
    """Validate Caddy config structural correctness beyond substring checks."""

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

    def test_ip_uses_handle_path(self):
        """Connection pages must use handle_path (not bare handle + uri strip_prefix)."""
        cfg = self._ip_config()
        assert "handle_path /connect/*" in cfg
        assert "uri strip_prefix" not in cfg

    def test_domain_uses_handle_path(self):
        cfg = self._domain_config()
        assert "handle_path /connect/*" in cfg
        assert "uri strip_prefix" not in cfg

    def test_ip_nocache_excludes_pwa(self):
        """@nocache block must have 'not path /pwa/*' to avoid caching static assets."""
        cfg = self._ip_config()
        assert "not path /pwa/*" in cfg

    def test_domain_nocache_excludes_pwa(self):
        cfg = self._domain_config()
        assert "not path /pwa/*" in cfg

    def test_ip_dynamic_includes_stats(self):
        """@dynamic matcher must include */stats/* for per-client stats."""
        cfg = self._ip_config()
        assert "*/stats/*" in cfg

    def test_domain_dynamic_includes_stats(self):
        cfg = self._domain_config()
        assert "*/stats/*" in cfg

    def test_ip_pwa_assets_matcher(self):
        """@pwa_assets matcher must match /pwa/* path."""
        cfg = self._ip_config()
        assert "@pwa_assets path /pwa/*" in cfg

    def test_domain_pwa_assets_matcher(self):
        cfg = self._domain_config()
        assert "@pwa_assets path /pwa/*" in cfg

    def test_ip_nocache_excludes_dynamic_paths(self):
        """@nocache block must exclude config.json and sub.txt (they have their own cache rules)."""
        cfg = self._ip_config()
        assert "not path */config.json" in cfg
        assert "not path */sub.txt" in cfg
        assert "not path */stats/*" in cfg

    def test_domain_nocache_excludes_dynamic_paths(self):
        cfg = self._domain_config()
        assert "not path */config.json" in cfg
        assert "not path */sub.txt" in cfg
        assert "not path */stats/*" in cfg


# ---------------------------------------------------------------------------
# _render_stats_script() basic test (Gap #7)
# ---------------------------------------------------------------------------


class TestRenderStatsScript:
    """Verify the stats update script is valid Python with correct parameters."""

    def test_output_is_valid_python(self):
        script = _render_stats_script(panel_internal_port=2053)
        # compile() will raise SyntaxError if the script is not valid Python
        compile(script, "<stats-script>", "exec")

    def test_contains_panel_url_with_port(self):
        script = _render_stats_script(panel_internal_port=9999)
        assert "127.0.0.1:9999" in script

    def test_contains_credential_file_path(self):
        script = _render_stats_script(panel_internal_port=2053)
        assert "/etc/meridian/proxy.yml" in script

    def test_handles_url_encoded_password(self):
        """Script should use urllib.parse.quote for password in login data."""
        script = _render_stats_script(panel_internal_port=2053)
        assert "urllib.parse.quote" in script

    def test_uses_different_ports(self):
        """Port parameter should be correctly interpolated."""
        script_a = _render_stats_script(panel_internal_port=2053)
        script_b = _render_stats_script(panel_internal_port=5555)
        assert "127.0.0.1:2053" in script_a
        assert "127.0.0.1:5555" in script_b
        assert "127.0.0.1:5555" not in script_a

    def test_writes_stats_to_uuid_json(self):
        """Script should write per-client stats files keyed by UUID."""
        script = _render_stats_script(panel_internal_port=2053)
        assert "/var/www/private/stats" in script
        assert ".json" in script

    def test_has_main_guard(self):
        script = _render_stats_script(panel_internal_port=2053)
        assert "__name__" in script
        assert "__main__" in script
