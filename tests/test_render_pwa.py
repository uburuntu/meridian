"""Tests for PWA rendering functions (config.json, subscription, shell, manifest)."""

from __future__ import annotations

import base64
import json

import pytest

from meridian.models import ProtocolURL, RelayURLSet
from meridian.render import (
    render_config_json,
    render_manifest,
    render_pwa_shell,
    render_subscription,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REALITY_URL = (
    "vless://550e8400-e29b-41d4-a716-446655440000@198.51.100.1:443?security=reality&sni=www.example.com#Test-Reality"
)
XHTTP_URL = "vless://550e8400-e29b-41d4-a716-446655440000@198.51.100.1:443?security=tls&type=xhttp#Test-XHTTP"
WSS_URL = "vless://660e8400-e29b-41d4-a716-446655440000@example.com:443?security=tls&type=ws#Test-WSS"
RELAY_URL = "vless://550e8400-e29b-41d4-a716-446655440000@10.0.0.1:443?security=reality&sni=www.example.com#Test-Relay"


@pytest.fixture()
def protocol_urls() -> list[ProtocolURL]:
    return [
        ProtocolURL(key="reality", label="Primary", url=REALITY_URL, qr_b64="dGVzdA=="),
        ProtocolURL(key="xhttp", label="XHTTP", url=XHTTP_URL, qr_b64="eGh0dHA="),
    ]


@pytest.fixture()
def relay_entries() -> list[RelayURLSet]:
    return [
        RelayURLSet(
            relay_ip="10.0.0.1",
            relay_name="ru-moscow",
            urls=[ProtocolURL(key="reality", label="Primary (via relay)", url=RELAY_URL, qr_b64="cmVsYXk=")],
        ),
    ]


# ---------------------------------------------------------------------------
# TestRenderConfigJson
# ---------------------------------------------------------------------------


class TestRenderConfigJson:
    def test_valid_json(self, protocol_urls: list[ProtocolURL]) -> None:
        result = render_config_json(protocol_urls, "198.51.100.1")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_basic_structure(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1"))
        assert result["version"] == 1
        assert result["server_ip"] == "198.51.100.1"
        assert "protocols" in result
        assert "relays" in result
        assert "apps" in result
        assert "generated_at" in result

    def test_includes_all_protocol_urls(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1"))
        keys = [p["key"] for p in result["protocols"]]
        assert "reality" in keys
        assert "xhttp" in keys

    def test_first_protocol_is_recommended(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1"))
        assert result["protocols"][0]["recommended"] is True
        assert result["protocols"][1]["recommended"] is False

    def test_relay_entries_included(
        self,
        protocol_urls: list[ProtocolURL],
        relay_entries: list[RelayURLSet],
    ) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1", relay_entries=relay_entries))
        assert len(result["relays"]) == 1
        assert result["relays"][0]["name"] == "ru-moscow"
        assert result["relays"][0]["ip"] == "10.0.0.1"

    def test_client_name(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1", client_name="alice"))
        assert result["client_name"] == "alice"

    def test_domain(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1", domain="example.com"))
        assert result["domain"] == "example.com"

    def test_qr_data_preserved(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1"))
        assert result["protocols"][0]["qr_b64"] == "dGVzdA=="

    def test_empty_protocols(self) -> None:
        result = json.loads(render_config_json([], "198.51.100.1"))
        assert result["protocols"] == []

    def test_apps_list_present(self, protocol_urls: list[ProtocolURL]) -> None:
        result = json.loads(render_config_json(protocol_urls, "198.51.100.1"))
        assert len(result["apps"]) >= 3
        platforms = [a["platform"] for a in result["apps"]]
        assert "iOS" in platforms
        assert "Android" in platforms


# ---------------------------------------------------------------------------
# TestRenderSubscription
# ---------------------------------------------------------------------------


class TestRenderSubscription:
    def test_base64_encoded(self, protocol_urls: list[ProtocolURL]) -> None:
        result = render_subscription(protocol_urls)
        decoded = base64.b64decode(result)
        assert isinstance(decoded, bytes)

    def test_decodes_to_urls(self, protocol_urls: list[ProtocolURL]) -> None:
        result = render_subscription(protocol_urls)
        decoded = base64.b64decode(result).decode()
        lines = decoded.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("vless://")
        assert lines[1].startswith("vless://")

    def test_includes_relay_urls(
        self,
        protocol_urls: list[ProtocolURL],
        relay_entries: list[RelayURLSet],
    ) -> None:
        result = render_subscription(protocol_urls, relay_entries=relay_entries)
        decoded = base64.b64decode(result).decode()
        lines = decoded.strip().split("\n")
        # 1 relay + 2 direct = 3
        assert len(lines) == 3
        assert "10.0.0.1" in lines[0]  # relay URL comes first

    def test_relay_urls_first(
        self,
        protocol_urls: list[ProtocolURL],
        relay_entries: list[RelayURLSet],
    ) -> None:
        result = render_subscription(protocol_urls, relay_entries=relay_entries)
        decoded = base64.b64decode(result).decode()
        lines = decoded.strip().split("\n")
        assert "10.0.0.1" in lines[0]

    def test_empty_urls(self) -> None:
        result = render_subscription([])
        assert result == ""

    def test_excludes_empty_urls(self) -> None:
        urls = [
            ProtocolURL(key="reality", label="Primary", url=REALITY_URL),
            ProtocolURL(key="wss", label="WSS", url=""),
        ]
        result = render_subscription(urls)
        decoded = base64.b64decode(result).decode()
        lines = decoded.strip().split("\n")
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# TestRenderPWAShell
# ---------------------------------------------------------------------------


class TestRenderPWAShell:
    def test_has_manifest_link(self) -> None:
        html = render_pwa_shell(client_name="test")
        assert 'rel="manifest"' in html
        assert "manifest.webmanifest" in html

    def test_has_app_js_script(self) -> None:
        html = render_pwa_shell()
        assert "app.js" in html

    def test_has_theme_color(self) -> None:
        html = render_pwa_shell()
        assert "theme-color" in html

    def test_has_noscript_fallback(self) -> None:
        html = render_pwa_shell()
        assert "<noscript>" in html

    def test_no_credentials_in_html(self) -> None:
        html = render_pwa_shell(client_name="alice")
        assert "vless://" not in html
        assert "qr_b64" not in html

    def test_has_referrer_policy(self) -> None:
        html = render_pwa_shell()
        assert "no-referrer" in html

    def test_client_name_in_title(self) -> None:
        html = render_pwa_shell(client_name="alice")
        assert "Alice" in html

    def test_custom_asset_path(self) -> None:
        html = render_pwa_shell(asset_path="/custom/path")
        assert "/custom/path/app.js" in html
        assert "/custom/path/styles.css" in html


# ---------------------------------------------------------------------------
# TestRenderManifest
# ---------------------------------------------------------------------------


class TestRenderManifest:
    def test_valid_json(self) -> None:
        result = render_manifest(client_name="test")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_has_icons(self) -> None:
        result = json.loads(render_manifest())
        assert "icons" in result
        assert len(result["icons"]) >= 1

    def test_client_name_in_name(self) -> None:
        result = json.loads(render_manifest(client_name="alice"))
        assert "Alice" in result["name"]

    def test_display_standalone(self) -> None:
        result = json.loads(render_manifest())
        assert result["display"] == "standalone"

    def test_start_url_is_dot(self) -> None:
        result = json.loads(render_manifest())
        assert result["start_url"] == "."

    def test_icon_is_svg(self) -> None:
        result = json.loads(render_manifest())
        icon = result["icons"][0]
        assert icon["type"] == "image/svg+xml"
        assert icon["sizes"] == "any"
