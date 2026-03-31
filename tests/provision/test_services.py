"""Tests for nginx and connection page provisioning steps."""

from __future__ import annotations

from pathlib import Path

from meridian.provision.services import (
    DeployConnectionPage,
    DeployPWAAssets,
    InstallNginx,
    _render_nginx_http_config,
    _render_nginx_ip_config,
    _render_nginx_stream_config,
    _render_stats_script,
)
from meridian.provision.steps import ProvisionContext
from tests.provision.conftest import MockConnection, make_credentials

# ---------------------------------------------------------------------------
# Config rendering: nginx stream (SNI routing)
# ---------------------------------------------------------------------------


class TestRenderNginxStreamConfig:
    def test_contains_sni_routing(self):
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "www.microsoft.com" in cfg
        assert "ssl_preread on" in cfg
        assert "proxy_pass $meridian_backend" in cfg

    def test_reality_sni_routes_to_xray(self):
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "www.microsoft.com  xray_reality" in cfg
        assert "127.0.0.1:10443" in cfg

    def test_server_ip_routes_to_nginx(self):
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "198.51.100.1  nginx_https" in cfg

    def test_domain_routes_to_nginx(self):
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
            domain="example.com",
        )
        assert "example.com  nginx_https" in cfg
        assert "198.51.100.1  nginx_https" in cfg

    def test_no_sni_routes_to_nginx(self):
        """Browsers connecting to bare IP send no SNI (RFC 6066)."""
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert '""  nginx_https' in cfg

    def test_unknown_sni_routes_to_nginx(self):
        """Unknown SNI routes to nginx — same response as direct IP (no differential)."""
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "default  nginx_https" in cfg
        assert "blackhole" not in cfg

    def test_no_domain_no_domain_rule(self):
        """Without domain, only server IP + no-SNI + default route to nginx."""
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "example.com" not in cfg
        # Count nginx_https map entries: server IP + no-SNI + default = 3
        nginx_rules = [
            line
            for line in cfg.splitlines()
            if "nginx_https" in line and "upstream" not in line and "server" not in line
        ]
        assert len(nginx_rules) == 3


# ---------------------------------------------------------------------------
# Config rendering: nginx http (IP mode)
# ---------------------------------------------------------------------------


class TestRenderNginxIpConfig:
    def test_has_ssl_certificate(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "ssl_certificate" in cfg
        assert "/etc/ssl/meridian/fullchain.pem" in cfg

    def test_has_server_tokens_off(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "server_tokens off" in cfg

    def test_has_acme_challenge_location(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "/.well-known/acme-challenge/" in cfg


# ---------------------------------------------------------------------------
# nginx config: PWA headers (cache control maps)
# ---------------------------------------------------------------------------


class TestNginxPWAHeaders:
    def _ip_config(self) -> str:
        return _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )

    def _domain_config(self) -> str:
        return _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )

    def test_ip_config_has_cache_map(self):
        cfg = self._ip_config()
        assert "$meridian_cache" in cfg
        assert "max-age=86400" in cfg

    def test_ip_config_has_sw_header_map(self):
        cfg = self._ip_config()
        assert "$meridian_sw" in cfg
        assert "Service-Worker-Allowed" in cfg

    def test_ip_config_has_dynamic_no_cache(self):
        cfg = self._ip_config()
        assert "no-cache, must-revalidate" in cfg

    def test_domain_config_has_cache_map(self):
        cfg = self._domain_config()
        assert "$meridian_cache" in cfg
        assert "max-age=86400" in cfg

    def test_domain_config_has_sw_header_map(self):
        cfg = self._domain_config()
        assert "$meridian_sw" in cfg
        assert "Service-Worker-Allowed" in cfg


# ---------------------------------------------------------------------------
# nginx config: XHTTP block
# ---------------------------------------------------------------------------


class TestNginxXHTTPBlock:
    def test_ip_config_xhttp_proxy_pass(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-abc123",
            xhttp_internal_port=29000,
        )
        assert "proxy_pass http://127.0.0.1:29000" in cfg
        assert "proxy_buffering off" in cfg
        assert "xh-abc123" in cfg

    def test_domain_config_xhttp_proxy_pass(self):
        cfg = _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-def456",
            xhttp_internal_port=29500,
        )
        assert "proxy_pass http://127.0.0.1:29500" in cfg
        assert "proxy_buffering off" in cfg
        assert "xh-def456" in cfg

    def test_xhttp_before_panel(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-test",
            xhttp_internal_port=29000,
        )
        xhttp_pos = cfg.index("xh-test")
        panel_pos = cfg.index("secretpanel")
        assert xhttp_pos < panel_pos

    def test_no_xhttp_without_params(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "XHTTP" not in cfg

    def test_xhttp_has_read_timeout(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            xhttp_path="xh-test",
            xhttp_internal_port=29000,
        )
        assert "proxy_read_timeout 360s" in cfg


# ---------------------------------------------------------------------------
# nginx config: location structure (connection pages)
# ---------------------------------------------------------------------------


class TestNginxLocationStructure:
    def _ip_config(self) -> str:
        return _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )

    def _domain_config(self) -> str:
        return _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )

    def test_ip_uses_alias(self):
        """Connection pages must use alias (strips location prefix)."""
        cfg = self._ip_config()
        assert "location /connect/" in cfg
        assert "alias /var/www/private/" in cfg

    def test_domain_uses_alias(self):
        cfg = self._domain_config()
        assert "location /connect/" in cfg
        assert "alias /var/www/private/" in cfg

    def test_ip_has_security_headers(self):
        cfg = self._ip_config()
        assert "X-Frame-Options" in cfg
        assert "X-Content-Type-Options" in cfg
        assert "Referrer-Policy" in cfg

    def test_domain_has_security_headers(self):
        cfg = self._domain_config()
        assert "X-Frame-Options" in cfg
        assert "X-Content-Type-Options" in cfg
        assert "Referrer-Policy" in cfg

    def test_ip_cache_map_has_stats(self):
        cfg = self._ip_config()
        assert "stats/" in cfg

    def test_domain_cache_map_has_stats(self):
        cfg = self._domain_config()
        assert "stats/" in cfg


# ---------------------------------------------------------------------------
# nginx config: domain mode WSS
# ---------------------------------------------------------------------------


class TestNginxWSS:
    def test_domain_config_has_websocket_upgrade(self):
        cfg = _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "proxy_set_header Upgrade" in cfg
        assert "proxy_set_header Connection $connection_upgrade" in cfg
        assert "proxy_pass http://127.0.0.1:28000" in cfg

    def test_ip_config_has_no_wss(self):
        """IP mode should not have WSS location."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "VLESS+WSS" not in cfg
        assert "proxy_set_header Upgrade" not in cfg


# ---------------------------------------------------------------------------
# nginx config: decoy mode
# ---------------------------------------------------------------------------


class TestNginxDecoy:
    def test_default_drops_connection(self):
        """Default is silent drop (444) — server reveals nothing.

        444 causes HTTP/2 PROTOCOL_ERROR, but that's not VPN-specific.
        Users who prefer a plausible web server use --decoy 403.
        """
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "return 444" in cfg
        assert "return 403" not in cfg
        assert "return 404" not in cfg

    def test_decoy_403_returns_403(self):
        """decoy=403 returns 403 on root, 404 on other paths (realistic nginx)."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            decoy="403",
        )
        assert "return 403" in cfg
        assert "return 404" in cfg
        assert "return 444" not in cfg

    def test_domain_decoy_403(self):
        cfg = _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            decoy="403",
        )
        assert "return 403" in cfg
        assert "return 404" in cfg
        assert "return 444" not in cfg

    def test_domain_default_drops_connection(self):
        """Domain mode default is also silent drop (444)."""
        cfg = _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "return 444" in cfg
        assert "return 403" not in cfg
        assert "return 404" not in cfg

    def test_default_has_security_headers(self):
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "X-Frame-Options" in cfg
        assert "X-Content-Type-Options" in cfg
        assert "Referrer-Policy" in cfg

    def test_server_tokens_off(self):
        """Both modes should have server_tokens off."""
        for decoy in ("", "403"):
            cfg = _render_nginx_ip_config(
                server_ip="198.51.100.1",
                nginx_internal_port=8443,
                panel_web_base_path="secretpanel",
                panel_internal_port=2053,
                info_page_path="connect",
                decoy=decoy,
            )
            assert "server_tokens off" in cfg


# ---------------------------------------------------------------------------
# nginx config: fingerprinting resistance
# ---------------------------------------------------------------------------


class TestNginxFingerprinting:
    """Tests for anti-fingerprinting properties discovered during real-server testing."""

    def test_http2_enabled(self):
        """HTTP/2 must be enabled — missing h2 ALPN is a fingerprinting vector."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "ssl http2" in cfg

    def test_domain_http2_enabled(self):
        cfg = _render_nginx_http_config(
            domain="example.com",
            nginx_internal_port=8443,
            ws_path="wspath",
            wss_internal_port=28000,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "ssl http2" in cfg

    def test_tls_modern_protocols_only(self):
        """Only TLSv1.2 and TLSv1.3 — no older protocols."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "TLSv1.2 TLSv1.3" in cfg
        assert "TLSv1.0" not in cfg
        assert "TLSv1.1" not in cfg
        assert "SSLv" not in cfg

    def test_stream_ipv6_listening(self):
        """Stream server must listen on both IPv4 and IPv6."""
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "listen 443;" in cfg
        assert "listen [::]:443;" in cfg

    def test_stream_proxy_connect_timeout(self):
        """Stream proxy should have a short connect timeout (good practice)."""
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "proxy_connect_timeout 1s" in cfg

    def test_http_redirect_uses_host_variable(self):
        """HTTP->HTTPS redirect must use $host, not hardcoded domain (no info leak)."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "$host$request_uri" in cfg

    def test_port80_server_tokens_off(self):
        """Port 80 server must also have server_tokens off."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        # Both server blocks should have server_tokens off
        assert cfg.count("server_tokens off") == 2

    def test_decoy_403_avoids_444(self):
        """--decoy 403 uses realistic 403/404, never 444 (HTTP/2-safe)."""
        for cfg in [
            _render_nginx_ip_config(
                server_ip="198.51.100.1",
                nginx_internal_port=8443,
                panel_web_base_path="secretpanel",
                panel_internal_port=2053,
                info_page_path="connect",
                decoy="403",
            ),
            _render_nginx_http_config(
                domain="example.com",
                nginx_internal_port=8443,
                ws_path="wspath",
                wss_internal_port=28000,
                panel_web_base_path="secretpanel",
                panel_internal_port=2053,
                info_page_path="connect",
                decoy="403",
            ),
        ]:
            assert "return 403" in cfg
            assert "return 404" in cfg
            assert "return 444" not in cfg

    def test_csp_restricts_external_resources(self):
        """CSP must block external resource loading (self-hosted everything)."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
        )
        assert "default-src 'self'" in cfg

    def test_no_sni_routing_differential(self):
        """Unknown SNI must get same backend as direct IP — no fingerprint."""
        cfg = _render_nginx_stream_config(
            reality_sni="www.microsoft.com",
            reality_backend_port=10443,
            nginx_internal_port=8443,
            server_ip="198.51.100.1",
        )
        assert "default  nginx_https" in cfg
        assert "blackhole" not in cfg

    def test_decoy_403_root_vs_default_paths(self):
        """--decoy 403 returns 403 on root, 404 on other paths (like real nginx)."""
        cfg = _render_nginx_ip_config(
            server_ip="198.51.100.1",
            nginx_internal_port=8443,
            panel_web_base_path="secretpanel",
            panel_internal_port=2053,
            info_page_path="connect",
            decoy="403",
        )
        assert "location = /" in cfg
        assert "return 403" in cfg
        assert "return 404" in cfg


# ---------------------------------------------------------------------------
# InstallNginx step
# ---------------------------------------------------------------------------


class TestInstallNginx:
    def test_already_installed_deploys_config(self, tmp_path: Path):
        conn = MockConnection()
        # nginx installed, stream module available
        conn.when("dpkg -l nginx", stdout="ii  nginx")
        conn.when("nginx -V", stdout="--with-stream_ssl_preread_module")
        # acme.sh installed
        conn.when("test -f /root/.acme.sh/acme.sh", stdout="", rc=0)
        # cert exists
        conn.when("test -f /etc/ssl/meridian/fullchain.pem", stdout="", rc=0)
        # All other commands succeed
        conn.when("mkdir", stdout="")
        conn.when("chown", stdout="")
        conn.when("printf", stdout="")
        conn.when("grep", stdout="stream {", rc=0)
        conn.when("rm -f", stdout="")
        conn.when("nginx -t", stdout="syntax is ok")
        conn.when("systemctl", stdout="")
        # acme.sh issue (cert already valid)
        conn.when("acme.sh --issue", stdout="", rc=2)
        conn.when("acme.sh --install-cert", stdout="")
        # Stop old services
        conn.when("systemctl stop haproxy", stdout="")
        conn.when("systemctl stop caddy", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path))
        step = InstallNginx(domain="", ip_mode=True, server_ip="198.51.100.1")
        result = step.run(conn, ctx)
        assert result.status == "changed"
        assert "nginx" in result.detail


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
# _render_stats_script() basic test
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
