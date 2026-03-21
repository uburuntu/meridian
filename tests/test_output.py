"""Tests for output module -- VLESS URL building and file generation."""

from __future__ import annotations

from pathlib import Path

from meridian.credentials import (
    PanelConfig,
    RealityProtocol,
    ServerConfig,
    ServerCredentials,
    WSSProtocol,
)
from meridian.output import ClientURLs, build_vless_urls, save_connection_text


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
            "reality": RealityProtocol(
                uuid="base-uuid",
                public_key=public_key,
                short_id=short_id,
                private_key="private",
            ),
        },
    )
    if ws_path:
        creds.protocols["wss"] = WSSProtocol(uuid="wss-uuid", ws_path=ws_path)
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
