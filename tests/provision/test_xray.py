"""Tests for Xray inbound helper functions (pure logic, no mocking).

These functions build JSON strings for the 3x-ui API. We verify
structure, required fields, and protocol-specific invariants.
"""

from __future__ import annotations

import json

from meridian.provision.xray import (
    _BLOCKED_OUTBOUND,
    _GEO_BLOCK_RULES,
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

    def test_client_settings_default_has_fallbacks(self):
        """Default decryption=none includes fallbacks."""
        raw = _client_settings(uuid=TEST_UUID, client_email="test")
        data = json.loads(raw)
        assert data["decryption"] == "none"
        assert data["fallbacks"] == []

    def test_client_settings_pq_encryption_omits_fallbacks(self):
        """PQ encryption sets decryption and omits fallbacks."""
        raw = _client_settings(
            uuid=TEST_UUID,
            client_email="test",
            decryption="mlkem768x25519plus.native.0rtt.testkey",
        )
        data = json.loads(raw)
        assert data["decryption"] == "mlkem768x25519plus.native.0rtt.testkey"
        assert "fallbacks" not in data


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

        step = CreateInbound(protocol_key="xhttp", port=31000, listen="127.0.0.1", ctx_exports={"xhttp_port": "port"})
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

    def test_api_failure_returns_failed(self):
        """Panel API returning success=False produces a failed result."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="reality", port=443)
        panel = MagicMock()
        panel.find_inbound.return_value = None
        panel.api_post_json.return_value = {"success": False, "msg": "duplicate remark"}

        from meridian.provision.steps import ProvisionContext

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel

        from tests.provision.conftest import MockConnection, make_credentials

        ctx["credentials"] = make_credentials()
        conn = MockConnection()
        result = step.run(conn, ctx)
        assert result.status == "failed"
        assert "duplicate remark" in result.detail

    def test_port_mismatch_without_flag_skips(self):
        """When delete_on_port_mismatch=False, port mismatch still skips."""
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="wss", port=28000, listen="127.0.0.1")
        panel = MagicMock()
        existing = MagicMock()
        existing.port = 99999  # different port
        existing.listen = "127.0.0.1"
        panel.find_inbound.return_value = existing

        from meridian.provision.steps import ProvisionContext

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel

        from tests.provision.conftest import MockConnection, make_credentials

        ctx["credentials"] = make_credentials()
        conn = MockConnection()
        result = step.run(conn, ctx)
        assert result.status == "skipped"
        panel.api_post_empty.assert_not_called()  # no delete

    def test_wss_stream_settings_valid_json(self):
        """WSS stream settings produce valid JSON with ws path."""
        import json
        from unittest.mock import MagicMock

        from meridian.provision.xray import CreateInbound

        step = CreateInbound(protocol_key="wss", port=28000)
        creds = MagicMock()
        creds.wss.ws_path = "ws789"
        result = step._build_stream_settings(creds)
        assert result is not None
        data = json.loads(result)
        assert data["network"] == "ws"
        assert "/ws789" in data["wsSettings"]["path"]


# ---------------------------------------------------------------------------
# ConfigureGeoBlocking
# ---------------------------------------------------------------------------


class TestConfigureGeoBlocking:
    """Tests for the ConfigureGeoBlocking step."""

    def _make_xray_template(self, outbounds=None, routing=None):
        """Build a fake Xray config template as returned by the panel API."""
        template = {"log": {}, "outbounds": outbounds or [{"protocol": "freedom", "tag": "direct"}]}
        if routing is not None:
            template["routing"] = routing
        return template

    def _panel_returning(self, template):
        """Create a MagicMock panel that returns the given template from /panel/xray/."""
        from unittest.mock import MagicMock

        panel = MagicMock()
        xray_setting = json.dumps(template)
        wrapper = json.dumps({"xraySetting": xray_setting})
        panel.api_post_empty.return_value = {"success": True, "obj": wrapper}
        panel.api_post_form.return_value = {"success": True}
        return panel

    def _run_step(self, panel):
        from meridian.provision.steps import ProvisionContext
        from meridian.provision.xray import ConfigureGeoBlocking
        from tests.provision.conftest import MockConnection

        step = ConfigureGeoBlocking()
        conn = MockConnection()
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel
        return step.run(conn, ctx)

    def test_adds_blocked_outbound_and_routing_rules(self):
        """Fresh config gets blackhole outbound + geo-block routing rules."""
        template = self._make_xray_template()
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "changed"
        assert "geosite:category-ru" in result.detail

        # Verify the saved template contains the blocked outbound and rules
        saved_call = panel.api_post_form.call_args
        assert saved_call is not None
        from urllib.parse import unquote

        form_data = saved_call[0][1]
        saved_json = unquote(form_data.split("xraySetting=")[1])
        saved = json.loads(saved_json)

        outbound_tags = [o.get("tag") for o in saved.get("outbounds", [])]
        assert "blocked" in outbound_tags

        rules = saved.get("routing", {}).get("rules", [])
        blocked_rules = [r for r in rules if r.get("outboundTag") == "blocked"]
        assert len(blocked_rules) == 2

    def test_idempotent_when_already_configured(self):
        """Skip when blocked outbound and geo rules already exist."""
        template = self._make_xray_template(
            outbounds=[
                {"protocol": "freedom", "tag": "direct"},
                _BLOCKED_OUTBOUND,
            ],
            routing={"rules": _GEO_BLOCK_RULES},
        )
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "ok"
        assert "already configured" in result.detail
        panel.api_post_form.assert_not_called()

    def test_api_fetch_failure_returns_failed(self):
        """Panel API error when fetching Xray config produces failed result."""
        from unittest.mock import MagicMock

        from meridian.panel import PanelError

        panel = MagicMock()
        panel.api_post_empty.side_effect = PanelError("connection refused")

        result = self._run_step(panel)
        assert result.status == "failed"
        assert "Failed to fetch Xray config" in result.detail

    def test_api_save_failure_returns_failed(self):
        """Panel API error when saving Xray config produces failed result."""
        template = self._make_xray_template()
        panel = self._panel_returning(template)
        panel.api_post_form.return_value = {"success": False, "msg": "disk full"}

        result = self._run_step(panel)
        assert result.status == "failed"
        assert "disk full" in result.detail

    def test_geo_rules_prepended_before_existing_rules(self):
        """Geo-block rules are inserted before existing routing rules."""
        existing_rule = {"type": "field", "outboundTag": "direct", "domain": ["geosite:category-ads"]}
        template = self._make_xray_template(routing={"rules": [existing_rule]})
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "changed"

        from urllib.parse import unquote

        form_data = panel.api_post_form.call_args[0][1]
        saved_json = unquote(form_data.split("xraySetting=")[1])
        saved = json.loads(saved_json)

        rules = saved["routing"]["rules"]
        # Geo-block rules come first, existing rule is last
        assert rules[-1] == existing_rule
        assert rules[0]["outboundTag"] == "blocked"


# ---------------------------------------------------------------------------
# DisableGeoBlocking
# ---------------------------------------------------------------------------


class TestDisableGeoBlocking:
    """Tests for the DisableGeoBlocking step."""

    def _make_xray_template(self, outbounds=None, routing=None):
        """Build a fake Xray config template as returned by the panel API."""
        template = {"log": {}, "outbounds": outbounds or [{"protocol": "freedom", "tag": "direct"}]}
        if routing is not None:
            template["routing"] = routing
        return template

    def _panel_returning(self, template):
        from unittest.mock import MagicMock

        panel = MagicMock()
        xray_setting = json.dumps(template)
        wrapper = json.dumps({"xraySetting": xray_setting})
        panel.api_post_empty.return_value = {"success": True, "obj": wrapper}
        panel.api_post_form.return_value = {"success": True}
        return panel

    def _run_step(self, panel):
        from meridian.provision.steps import ProvisionContext
        from meridian.provision.xray import DisableGeoBlocking
        from tests.provision.conftest import MockConnection

        step = DisableGeoBlocking()
        conn = MockConnection()
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp")
        ctx["panel"] = panel
        return step.run(conn, ctx)

    def test_removes_geo_rules_and_blocked_outbound(self):
        """Removes blocked outbound and geo-block rules when present."""
        template = self._make_xray_template(
            outbounds=[
                {"protocol": "freedom", "tag": "direct"},
                _BLOCKED_OUTBOUND,
            ],
            routing={"rules": list(_GEO_BLOCK_RULES)},
        )
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "changed"

        from urllib.parse import unquote

        form_data = panel.api_post_form.call_args[0][1]
        saved_json = unquote(form_data.split("xraySetting=")[1])
        saved = json.loads(saved_json)

        outbound_tags = [o.get("tag") for o in saved.get("outbounds", [])]
        assert "blocked" not in outbound_tags

        rules = saved.get("routing", {}).get("rules", [])
        assert len(rules) == 0

    def test_idempotent_when_already_disabled(self):
        """Skip when no blocked outbound and no geo rules exist."""
        template = self._make_xray_template()
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "ok"
        assert "already disabled" in result.detail
        panel.api_post_form.assert_not_called()

    def test_preserves_other_routing_rules(self):
        """Non-geo routing rules are kept intact."""
        other_rule = {"type": "field", "outboundTag": "direct", "domain": ["geosite:category-ads"]}
        template = self._make_xray_template(
            outbounds=[
                {"protocol": "freedom", "tag": "direct"},
                _BLOCKED_OUTBOUND,
            ],
            routing={"rules": list(_GEO_BLOCK_RULES) + [other_rule]},
        )
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "changed"

        from urllib.parse import unquote

        form_data = panel.api_post_form.call_args[0][1]
        saved_json = unquote(form_data.split("xraySetting=")[1])
        saved = json.loads(saved_json)

        rules = saved.get("routing", {}).get("rules", [])
        assert len(rules) == 1
        assert rules[0] == other_rule

    def test_keeps_blocked_outbound_if_other_rules_use_it(self):
        """Blocked outbound is kept if non-geo rules reference it."""
        custom_blocked_rule = {"type": "field", "outboundTag": "blocked", "domain": ["ads.example.com"]}
        template = self._make_xray_template(
            outbounds=[
                {"protocol": "freedom", "tag": "direct"},
                _BLOCKED_OUTBOUND,
            ],
            routing={"rules": list(_GEO_BLOCK_RULES) + [custom_blocked_rule]},
        )
        panel = self._panel_returning(template)

        result = self._run_step(panel)
        assert result.status == "changed"

        from urllib.parse import unquote

        form_data = panel.api_post_form.call_args[0][1]
        saved_json = unquote(form_data.split("xraySetting=")[1])
        saved = json.loads(saved_json)

        outbound_tags = [o.get("tag") for o in saved.get("outbounds", [])]
        assert "blocked" in outbound_tags

        rules = saved.get("routing", {}).get("rules", [])
        assert len(rules) == 1
        assert rules[0] == custom_blocked_rule
