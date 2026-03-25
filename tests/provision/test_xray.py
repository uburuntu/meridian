"""Tests for Xray inbound helper functions (pure logic, no mocking).

These functions build JSON strings for the 3x-ui API. We verify
structure, required fields, and protocol-specific invariants.
"""

from __future__ import annotations

import json

from meridian.provision.xray import (
    _client_settings,
    _reality_stream_settings,
    _wss_stream_settings,
    _xhttp_caddy_stream_settings,
    _xhttp_stream_settings,
)

# Test UUIDs (RFC 5737-style safe values)
TEST_UUID = "550e8400-e29b-41d4-a716-446655440000"
TEST_SNI = "www.example.com"
TEST_PRIVATE_KEY = "test-private-key-base64"
TEST_PUBLIC_KEY = "test-public-key-base64x"
TEST_SHORT_ID = "abcd1234"


# ---------------------------------------------------------------------------
# _client_settings
# ---------------------------------------------------------------------------


class TestClientSettings:
    def test_client_settings_returns_valid_json(self):
        """Result is valid JSON that can be parsed."""
        raw = _client_settings(uuid=TEST_UUID, client_email="test@example")
        data = json.loads(raw)
        assert "clients" in data
        assert len(data["clients"]) == 1

    def test_client_settings_reality_flow(self):
        """Reality inbound uses xtls-rprx-vision flow."""
        raw = _client_settings(uuid=TEST_UUID, client_email="reality-default", flow="xtls-rprx-vision")
        data = json.loads(raw)
        assert data["clients"][0]["flow"] == "xtls-rprx-vision"

    def test_client_settings_xhttp_empty_flow(self):
        """XHTTP inbound must have empty flow (no xtls-rprx-vision)."""
        raw = _client_settings(uuid=TEST_UUID, client_email="xhttp-default", flow="")
        data = json.loads(raw)
        assert data["clients"][0]["flow"] == ""


# ---------------------------------------------------------------------------
# _reality_stream_settings
# ---------------------------------------------------------------------------


class TestRealityStreamSettings:
    def test_reality_stream_settings_dest_format(self):
        """dest field is formatted as '{sni}:443'."""
        raw = _reality_stream_settings(
            sni=TEST_SNI,
            private_key=TEST_PRIVATE_KEY,
            public_key=TEST_PUBLIC_KEY,
            short_id=TEST_SHORT_ID,
        )
        data = json.loads(raw)
        assert data["realitySettings"]["dest"] == f"{TEST_SNI}:443"

    def test_reality_stream_settings_short_ids(self):
        """shortIds list contains the provided short_id."""
        raw = _reality_stream_settings(
            sni=TEST_SNI,
            private_key=TEST_PRIVATE_KEY,
            public_key=TEST_PUBLIC_KEY,
            short_id=TEST_SHORT_ID,
        )
        data = json.loads(raw)
        assert TEST_SHORT_ID in data["realitySettings"]["shortIds"]

    def test_reality_stream_settings_spider_x_derived_from_short_id(self):
        """spiderX is derived from short_id (not hardcoded '/')."""
        raw = _reality_stream_settings(
            sni=TEST_SNI,
            private_key=TEST_PRIVATE_KEY,
            public_key=TEST_PUBLIC_KEY,
            short_id=TEST_SHORT_ID,
        )
        data = json.loads(raw)
        spider_x = data["realitySettings"]["settings"]["spiderX"]
        assert spider_x == f"/{TEST_SHORT_ID}"
        assert spider_x != "/"


# ---------------------------------------------------------------------------
# _xhttp_stream_settings
# ---------------------------------------------------------------------------


class TestXHTTPStreamSettings:
    def test_xhttp_stream_settings_mode(self):
        """Default XHTTP mode is 'packet-up'."""
        raw = _xhttp_stream_settings(
            sni=TEST_SNI,
            private_key=TEST_PRIVATE_KEY,
            public_key=TEST_PUBLIC_KEY,
            short_id=TEST_SHORT_ID,
        )
        data = json.loads(raw)
        assert data["xhttpSettings"]["mode"] == "packet-up"

    def test_xhttp_stream_settings_spider_x_derived_from_short_id(self):
        """spiderX in XHTTP Reality settings is derived from short_id."""
        raw = _xhttp_stream_settings(
            sni=TEST_SNI,
            private_key=TEST_PRIVATE_KEY,
            public_key=TEST_PUBLIC_KEY,
            short_id=TEST_SHORT_ID,
        )
        data = json.loads(raw)
        spider_x = data["realitySettings"]["settings"]["spiderX"]
        assert spider_x == f"/{TEST_SHORT_ID}"
        assert spider_x != "/"


# ---------------------------------------------------------------------------
# _xhttp_caddy_stream_settings
# ---------------------------------------------------------------------------


class TestXHTTPCaddyStreamSettings:
    def test_xhttp_caddy_stream_settings_security_none(self):
        """XHTTP behind Caddy uses security: none (Caddy handles TLS)."""
        raw = _xhttp_caddy_stream_settings(xhttp_path="xhttp123")
        data = json.loads(raw)
        assert data["security"] == "none"


# ---------------------------------------------------------------------------
# _wss_stream_settings
# ---------------------------------------------------------------------------


class TestWSSStreamSettings:
    def test_wss_stream_settings_path(self):
        """WSS path gets '/' prefix."""
        raw = _wss_stream_settings(ws_path="ws789")
        data = json.loads(raw)
        assert data["wsSettings"]["path"] == "/ws789"
