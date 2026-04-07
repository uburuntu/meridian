"""Tests for Xray inbound helper functions (pure logic, no mocking).

These functions build JSON strings for the 3x-ui API. We verify
structure, required fields, and protocol-specific invariants.
"""

from __future__ import annotations

import json

from meridian.provision.xray import (
    _XRAY_LOG_CONFIG,
    _client_settings,
    _reality_stream_settings,
    _wss_stream_settings,
    _xhttp_reverse_proxy_stream_settings,
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
# _xhttp_reverse_proxy_stream_settings
# ---------------------------------------------------------------------------


class TestXHTTPReverseProxyStreamSettings:
    def test_xhttp_reverse_proxy_stream_settings_security_none(self):
        """XHTTP behind nginx uses security: none (nginx handles TLS)."""
        raw = _xhttp_reverse_proxy_stream_settings(xhttp_path="xhttp123")
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


# ---------------------------------------------------------------------------
# _XRAY_LOG_CONFIG
# ---------------------------------------------------------------------------


class TestXrayLogConfig:
    def test_access_log_disabled(self):
        """Access log must be 'none' — no per-connection logging."""
        assert _XRAY_LOG_CONFIG["access"] == "none"

    def test_error_log_disabled(self):
        """Error log must be 'none' — no persistent error log file."""
        assert _XRAY_LOG_CONFIG["error"] == "none"

    def test_dns_log_disabled(self):
        assert _XRAY_LOG_CONFIG["dnsLog"] is False


# ---------------------------------------------------------------------------
# CreateInbound
# ---------------------------------------------------------------------------


class TestCreateInbound:
    """Tests for the unified CreateInbound step."""

    def test_invalid_protocol_key_raises(self):
        """Unknown protocol_key fails at construction, not deploy time."""
        import pytest

        from meridian.provision.xray import CreateInbound

        with pytest.raises(ValueError, match="Unknown protocol_key"):
            CreateInbound(protocol_key="invalid", port=443)

    def test_reality_uses_reality_uuid(self):
        """Reality protocol resolves UUID from creds.reality."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="reality", port=443, delete_on_port_mismatch=True)
        creds = MagicMock()
        creds.reality.uuid = "reality-uuid-123"
        creds.wss.uuid = "wss-uuid-456"
        assert step._get_uuid(creds) == "reality-uuid-123"

    def test_xhttp_uses_reality_uuid(self):
        """XHTTP shares Reality UUID."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="xhttp", port=30000, listen="127.0.0.1")
        creds = MagicMock()
        creds.reality.uuid = "reality-uuid-123"
        creds.wss.uuid = "wss-uuid-456"
        assert step._get_uuid(creds) == "reality-uuid-123"

    def test_wss_uses_wss_uuid(self):
        """WSS uses its own UUID."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="wss", port=28000, listen="127.0.0.1")
        creds = MagicMock()
        creds.reality.uuid = "reality-uuid-123"
        creds.wss.uuid = "wss-uuid-456"
        assert step._get_uuid(creds) == "wss-uuid-456"

    def test_xhttp_missing_path_returns_none(self):
        """XHTTP with empty xhttp_path fails gracefully."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="xhttp", port=30000)
        creds = MagicMock()
        creds.xhttp.xhttp_path = ""
        assert step._build_stream_settings(creds) is None

    def test_reality_stream_settings_valid_json(self):
        """Reality stream settings produce valid JSON."""
        import json
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="reality", port=443)
        creds = MagicMock()
        creds.server.sni = "www.example.com"
        creds.reality.private_key = "test-priv"
        creds.reality.public_key = "test-pub"
        creds.reality.short_id = "abcd1234"
        result = step._build_stream_settings(creds)
        assert result is not None
        data = json.loads(result)
        assert data["security"] == "reality"

    def test_ctx_exports(self):
        """ctx_exports sets context keys using step attributes."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(
            protocol_key="xhttp", port=31000, listen="127.0.0.1", ctx_exports={"xhttp_port": "port"}
        )
        panel = MagicMock()
        panel.find_inbound.return_value = None
        panel.api_post_json.return_value = {"success": True}

        from meridian.provision.steps import ProvisionContext

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel

        from tests.provision.conftest import make_credentials

        ctx["credentials"] = make_credentials()

        from tests.provision.conftest import MockConnection

        conn = MockConnection()
        result = step.run(conn, ctx)
        assert result.status == "changed"
        assert ctx["xhttp_port"] == 31000

    def test_delete_on_port_mismatch(self):
        """Reality inbound is deleted and recreated on port mismatch."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="reality", port=10443, delete_on_port_mismatch=True)
        panel = MagicMock()
        existing = MagicMock()
        existing.port = 443  # different from step's 10443
        existing.listen = ""
        existing.id = 42
        panel.find_inbound.return_value = existing
        panel.api_post_json.return_value = {"success": True}

        from meridian.provision.steps import ProvisionContext

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel

        from tests.provision.conftest import make_credentials

        ctx["credentials"] = make_credentials()

        from tests.provision.conftest import MockConnection

        conn = MockConnection()
        result = step.run(conn, ctx)
        assert result.status == "changed"
        panel.api_post_empty.assert_called_once()  # _delete_inbound was called

    def test_skip_on_existing_no_mismatch(self):
        """Non-reality inbound skips when already exists."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="wss", port=28000, listen="127.0.0.1")
        panel = MagicMock()
        existing = MagicMock()
        existing.port = 28000
        existing.listen = "127.0.0.1"
        panel.find_inbound.return_value = existing

        from meridian.provision.steps import ProvisionContext

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel

        from tests.provision.conftest import make_credentials

        ctx["credentials"] = make_credentials()

        from tests.provision.conftest import MockConnection

        conn = MockConnection()
        result = step.run(conn, ctx)
        assert result.status == "skipped"
