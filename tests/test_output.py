"""Tests for output module -- VLESS URL building and file generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from meridian.credentials import (
    PanelConfig,
    RealityConfig,
    ServerConfig,
    ServerCredentials,
    WSSConfig,
)
from meridian.output import (
    ClientURLs,
    build_vless_urls,
    generate_qr_base64,
    generate_qr_terminal,
    save_connection_html,
    save_connection_text,
)


def _make_creds(
    ip: str = "1.2.3.4",
    sni: str = "www.microsoft.com",
    public_key: str = "K6JYbz4MflVPaaxdtRHo",
    short_id: str = "abcd1234",
    domain: str = "",
    ws_path: str = "",
) -> ServerCredentials:
    """Create test credentials."""
    creds = ServerCredentials(
        panel=PanelConfig(username="admin", password="pass", port=2053),
        server=ServerConfig(ip=ip, sni=sni, domain=domain or None),
        protocols={
            "reality": RealityConfig(
                uuid="base-uuid",
                public_key=public_key,
                short_id=short_id,
                private_key="private",
            ),
        },
    )
    if ws_path:
        creds.protocols["wss"] = WSSConfig(uuid="wss-uuid", ws_path=ws_path)
    return creds


class TestBuildVlessURLs:
    def test_reality_url_basic(self) -> None:
        creds = _make_creds()
        urls = build_vless_urls("alice", "uuid-1", "", creds)

        assert urls.name == "alice"
        assert urls.reality.startswith("vless://uuid-1@1.2.3.4:443")
        assert "flow=xtls-rprx-vision" in urls.reality
        assert "security=reality" in urls.reality
        assert "sni=www.microsoft.com" in urls.reality
        assert "fp=chrome" in urls.reality
        assert "pbk=K6JYbz4MflVPaaxdtRHo" in urls.reality
        assert "sid=abcd1234" in urls.reality
        assert "type=tcp" in urls.reality
        assert "#alice" in urls.reality

    def test_no_xhttp_when_port_zero(self) -> None:
        creds = _make_creds()
        urls = build_vless_urls("alice", "uuid-1", "", creds, xhttp_port=0)
        assert urls.xhttp == ""

    def test_xhttp_url_with_port(self) -> None:
        creds = _make_creds()
        urls = build_vless_urls("alice", "uuid-1", "", creds, xhttp_port=12345)

        assert urls.xhttp.startswith("vless://uuid-1@1.2.3.4:12345")
        assert "type=xhttp" in urls.xhttp
        assert "mode=packet-up" in urls.xhttp
        assert "#alice-XHTTP" in urls.xhttp
        # XHTTP uses Reality too
        assert "security=reality" in urls.xhttp
        # XHTTP must NOT have flow (empty)
        assert "flow=" not in urls.xhttp

    def test_no_wss_without_domain(self) -> None:
        creds = _make_creds()
        urls = build_vless_urls("alice", "uuid-1", "", creds)
        assert urls.wss == ""

    def test_no_wss_without_wss_uuid(self) -> None:
        creds = _make_creds(domain="example.com", ws_path="ws789")
        urls = build_vless_urls("alice", "uuid-1", "", creds)
        assert urls.wss == ""

    def test_wss_url_with_domain(self) -> None:
        creds = _make_creds(domain="example.com", ws_path="ws789")
        urls = build_vless_urls("alice", "uuid-1", "wss-uuid", creds)

        assert urls.wss.startswith("vless://wss-uuid@example.com:443")
        assert "security=tls" in urls.wss
        assert "type=ws" in urls.wss
        assert "path=%2Fws789" in urls.wss
        assert "#alice-WSS" in urls.wss

    def test_reality_uuid_used_for_xhttp(self) -> None:
        """XHTTP shares the Reality UUID, not a separate one."""
        creds = _make_creds()
        urls = build_vless_urls("alice", "reality-uuid", "wss-uuid", creds, xhttp_port=9999)
        assert urls.xhttp.startswith("vless://reality-uuid@")

    def test_different_sni(self) -> None:
        creds = _make_creds(sni="dl.google.com")
        urls = build_vless_urls("alice", "uuid-1", "", creds)
        assert "sni=dl.google.com" in urls.reality

    def test_url_fragment_encoding(self) -> None:
        """Client name with special chars should work in URL fragment."""
        creds = _make_creds()
        urls = build_vless_urls("my-client_1", "uuid-1", "", creds)
        assert "#my-client_1" in urls.reality


class TestClientURLs:
    def test_frozen_dataclass(self) -> None:
        urls = ClientURLs(name="test", reality="r", xhttp="x", wss="w")
        assert urls.name == "test"
        assert urls.reality == "r"
        assert urls.xhttp == "x"
        assert urls.wss == "w"


class TestSaveConnectionText:
    def test_creates_file(self, tmp_path: Path) -> None:
        urls = ClientURLs(
            name="alice",
            reality="vless://uuid@1.2.3.4:443?test",
            xhttp="",
            wss="",
        )
        dest = tmp_path / "creds" / "1.2.3.4-alice-connection-info.txt"
        save_connection_text(urls, dest, "1.2.3.4")

        assert dest.exists()
        content = dest.read_text()
        assert "alice" in content
        assert "vless://uuid@1.2.3.4:443?test" in content
        assert "1.2.3.4" in content

    def test_includes_xhttp_when_present(self, tmp_path: Path) -> None:
        urls = ClientURLs(
            name="alice",
            reality="vless://reality",
            xhttp="vless://xhttp",
            wss="",
        )
        dest = tmp_path / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")

        content = dest.read_text()
        assert "XHTTP" in content
        assert "vless://xhttp" in content

    def test_includes_wss_when_present(self, tmp_path: Path) -> None:
        urls = ClientURLs(
            name="alice",
            reality="vless://reality",
            xhttp="",
            wss="vless://wss",
        )
        dest = tmp_path / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")

        content = dest.read_text()
        assert "WSS" in content
        assert "vless://wss" in content

    def test_file_permissions(self, tmp_path: Path) -> None:
        urls = ClientURLs(name="test", reality="vless://x", xhttp="", wss="")
        dest = tmp_path / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")
        assert oct(dest.stat().st_mode)[-3:] == "600"


class TestBuildVlessURLsEdgeCases:
    """Additional URL building edge case tests."""

    def test_sni_with_subdomain(self) -> None:
        creds = _make_creds(sni="sub.domain.example.com")
        urls = build_vless_urls("test", "uuid-1", "", creds)
        assert "sni=sub.domain.example.com" in urls.reality

    def test_all_protocols_together(self) -> None:
        """Test building URLs with all three protocols enabled."""
        creds = _make_creds(domain="example.com", ws_path="myws")
        urls = build_vless_urls("alice", "r-uuid", "w-uuid", creds, xhttp_port=8443)
        assert urls.reality.startswith("vless://r-uuid@1.2.3.4:443")
        assert urls.xhttp.startswith("vless://r-uuid@1.2.3.4:8443")
        assert urls.wss.startswith("vless://w-uuid@example.com:443")
        assert "#alice" in urls.reality
        assert "#alice-XHTTP" in urls.xhttp
        assert "#alice-WSS" in urls.wss

    def test_empty_sni_defaults(self) -> None:
        """When SNI is None, should default to www.microsoft.com."""
        creds = ServerCredentials(
            panel=PanelConfig(username="admin", password="pass", port=2053),
            server=ServerConfig(ip="1.2.3.4", sni=None),
            protocols={
                "reality": RealityConfig(
                    uuid="base-uuid",
                    public_key="pk",
                    short_id="sid",
                    private_key="priv",
                ),
            },
        )
        urls = build_vless_urls("test", "uuid-1", "", creds)
        assert "sni=www.microsoft.com" in urls.reality

    def test_url_contains_encryption_none(self) -> None:
        creds = _make_creds()
        urls = build_vless_urls("test", "uuid-1", "", creds)
        assert "encryption=none" in urls.reality

    def test_xhttp_no_flow_parameter(self) -> None:
        """XHTTP must NOT include flow parameter (xtls-rprx-vision is incompatible)."""
        creds = _make_creds()
        urls = build_vless_urls("test", "uuid-1", "", creds, xhttp_port=9000)
        # XHTTP URL should not have flow= at all
        assert "flow=" not in urls.xhttp
        # But reality URL should have it
        assert "flow=xtls-rprx-vision" in urls.reality

    def test_wss_url_has_host_header(self) -> None:
        """WSS URL should include host= parameter matching domain."""
        creds = _make_creds(domain="cdn.example.com", ws_path="ws")
        urls = build_vless_urls("test", "r-uuid", "w-uuid", creds)
        assert "host=cdn.example.com" in urls.wss

    def test_xhttp_path_is_slash(self) -> None:
        """XHTTP path should be URL-encoded /."""
        creds = _make_creds()
        urls = build_vless_urls("test", "uuid", "", creds, xhttp_port=5000)
        assert "path=%2F" in urls.xhttp

    def test_client_name_with_numbers(self) -> None:
        creds = _make_creds()
        urls = build_vless_urls("user123", "uuid-1", "", creds)
        assert "#user123" in urls.reality


class TestQRCodeGeneration:
    """Test QR code generation with mocked subprocess."""

    def test_generate_qr_terminal_success(self) -> None:
        mock_result = type("Result", (), {"returncode": 0, "stdout": "QR_OUTPUT"})()
        with patch("meridian.urls.subprocess.run", return_value=mock_result):
            result = generate_qr_terminal("vless://test")
        assert result == "QR_OUTPUT"

    def test_generate_qr_terminal_failure(self) -> None:
        mock_result = type("Result", (), {"returncode": 1, "stdout": ""})()
        with patch("meridian.urls.subprocess.run", return_value=mock_result):
            result = generate_qr_terminal("vless://test")
        assert result == ""

    def test_generate_qr_terminal_not_installed(self) -> None:
        with patch("meridian.urls.subprocess.run", side_effect=FileNotFoundError):
            result = generate_qr_terminal("vless://test")
        assert result == ""

    def test_generate_qr_terminal_timeout(self) -> None:
        import subprocess

        with patch("meridian.urls.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="qrencode", timeout=5)):
            result = generate_qr_terminal("vless://test")
        assert result == ""

    def test_generate_qr_base64_success(self) -> None:
        mock_result = type("Result", (), {"returncode": 0, "stdout": "iVBORw0KGgo="})()
        with patch("meridian.urls.subprocess.run", return_value=mock_result):
            result = generate_qr_base64("vless://test")
        assert result == "iVBORw0KGgo="

    def test_generate_qr_base64_failure(self) -> None:
        mock_result = type("Result", (), {"returncode": 1, "stdout": ""})()
        with patch("meridian.urls.subprocess.run", return_value=mock_result):
            result = generate_qr_base64("vless://test")
        assert result == ""

    def test_generate_qr_base64_not_installed(self) -> None:
        with patch("meridian.urls.subprocess.run", side_effect=FileNotFoundError):
            result = generate_qr_base64("vless://test")
        assert result == ""


class TestSaveConnectionHtml:
    """Test HTML connection page generation."""

    def test_creates_file(self, tmp_path: Path) -> None:
        urls = ClientURLs(
            name="alice",
            reality="vless://uuid@1.2.3.4:443?test",
            xhttp="",
            wss="",
        )
        dest = tmp_path / "alice.html"
        with patch("meridian.render.generate_qr_base64", return_value=""):
            save_connection_html(urls, dest, "1.2.3.4")
        assert dest.exists()

    def test_html_contains_client_name_in_url(self, tmp_path: Path) -> None:
        """Client name appears in the VLESS URL fragment within the HTML."""
        urls = ClientURLs(
            name="bob",
            reality="vless://uuid@1.2.3.4:443?test#bob",
            xhttp="",
            wss="",
        )
        dest = tmp_path / "bob.html"
        with patch("meridian.render.generate_qr_base64", return_value=""):
            save_connection_html(urls, dest, "1.2.3.4")
        content = dest.read_text()
        # The client name appears in the VLESS URL embedded in the HTML
        assert "vless://uuid@1.2.3.4:443?test#bob" in content

    def test_html_contains_reality_url(self, tmp_path: Path) -> None:
        urls = ClientURLs(
            name="test",
            reality="vless://unique-reality-url@1.2.3.4:443",
            xhttp="",
            wss="",
        )
        dest = tmp_path / "test.html"
        with patch("meridian.render.generate_qr_base64", return_value=""):
            save_connection_html(urls, dest, "1.2.3.4")
        content = dest.read_text()
        assert "unique-reality-url" in content

    def test_html_file_permissions(self, tmp_path: Path) -> None:
        urls = ClientURLs(name="test", reality="vless://x", xhttp="", wss="")
        dest = tmp_path / "test.html"
        with patch("meridian.render.generate_qr_base64", return_value=""):
            save_connection_html(urls, dest, "1.2.3.4")
        assert oct(dest.stat().st_mode)[-3:] == "600"

    def test_html_is_valid_structure(self, tmp_path: Path) -> None:
        """Generated HTML should have basic structure."""
        urls = ClientURLs(
            name="alice",
            reality="vless://uuid@1.2.3.4:443",
            xhttp="",
            wss="",
        )
        dest = tmp_path / "alice.html"
        with patch("meridian.render.generate_qr_base64", return_value=""):
            save_connection_html(urls, dest, "1.2.3.4")
        content = dest.read_text()
        assert "<!DOCTYPE html>" in content or "<html" in content
        assert "</html>" in content

    def test_html_includes_ping_url(self, tmp_path: Path) -> None:
        """Generated HTML should include a ping URL for troubleshooting."""
        urls = ClientURLs(
            name="alice",
            reality="vless://uuid@1.2.3.4:443",
            xhttp="",
            wss="",
        )
        dest = tmp_path / "alice.html"
        with patch("meridian.render.generate_qr_base64", return_value=""):
            save_connection_html(urls, dest, "1.2.3.4")
        content = dest.read_text()
        assert "meridian.msu.rocks/ping" in content


class TestSaveConnectionTextAllProtocols:
    """Test text output with all combinations of protocols."""

    def test_all_protocols(self, tmp_path: Path) -> None:
        urls = ClientURLs(
            name="alice",
            reality="vless://reality-url",
            xhttp="vless://xhttp-url",
            wss="vless://wss-url",
        )
        dest = tmp_path / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")
        content = dest.read_text()
        assert "vless://reality-url" in content
        assert "vless://xhttp-url" in content
        assert "vless://wss-url" in content
        assert "XHTTP" in content
        assert "WSS" in content
        assert "Reality" in content

    def test_text_includes_client_apps(self, tmp_path: Path) -> None:
        urls = ClientURLs(name="test", reality="vless://x", xhttp="", wss="")
        dest = tmp_path / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")
        content = dest.read_text()
        assert "v2rayNG" in content
        assert "v2RayTun" in content or "Hiddify" in content

    def test_text_includes_time_sync_warning(self, tmp_path: Path) -> None:
        urls = ClientURLs(name="test", reality="vless://x", xhttp="", wss="")
        dest = tmp_path / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")
        content = dest.read_text()
        assert "TIME SYNC" in content or "time" in content.lower()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        urls = ClientURLs(name="test", reality="vless://x", xhttp="", wss="")
        dest = tmp_path / "deep" / "nested" / "dir" / "out.txt"
        save_connection_text(urls, dest, "1.2.3.4")
        assert dest.exists()
