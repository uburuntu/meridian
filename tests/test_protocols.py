"""Tests for protocol/inbound type registry and Protocol abstraction."""

from __future__ import annotations

from meridian.panel import Inbound
from meridian.protocols import (
    INBOUND_TYPES,
    PROTOCOLS,
    InboundType,
    Protocol,
    RealityProtocol,
    WSSProtocol,
    XHTTPProtocol,
    available_protocols,
    get_protocol,
)


class TestInboundTypes:
    def test_all_types_present(self) -> None:
        assert set(INBOUND_TYPES.keys()) == {"reality", "wss", "xhttp"}

    def test_type_is_frozen_dataclass(self) -> None:
        for t in INBOUND_TYPES.values():
            assert isinstance(t, InboundType)

    def test_reality_values(self) -> None:
        r = INBOUND_TYPES["reality"]
        assert r.remark == "VLESS-Reality"
        assert r.email_prefix == "reality-"
        assert r.flow == "xtls-rprx-vision"
        assert r.url_scheme == "vless"

    def test_wss_values(self) -> None:
        w = INBOUND_TYPES["wss"]
        assert w.remark == "VLESS-WSS"
        assert w.email_prefix == "wss-"
        assert w.flow == ""

    def test_xhttp_values(self) -> None:
        x = INBOUND_TYPES["xhttp"]
        assert x.remark == "VLESS-Reality-XHTTP"
        assert x.email_prefix == "xhttp-"
        assert x.flow == ""

    def test_email_prefixes_unique(self) -> None:
        prefixes = [t.email_prefix for t in INBOUND_TYPES.values()]
        assert len(prefixes) == len(set(prefixes))

    def test_remarks_unique(self) -> None:
        remarks = [t.remark for t in INBOUND_TYPES.values()]
        assert len(remarks) == len(set(remarks))


# ---------------------------------------------------------------------------
# Protocol ABC and registry
# ---------------------------------------------------------------------------


class TestProtocolRegistry:
    """Tests for the PROTOCOLS list and get_protocol() function."""

    def test_all_protocols_present(self) -> None:
        keys = [p.key for p in PROTOCOLS]
        assert keys == ["reality", "xhttp", "wss"]

    def test_protocols_are_protocol_instances(self) -> None:
        for p in PROTOCOLS:
            assert isinstance(p, Protocol)

    def test_protocol_types(self) -> None:
        assert isinstance(PROTOCOLS[0], RealityProtocol)
        assert isinstance(PROTOCOLS[1], XHTTPProtocol)
        assert isinstance(PROTOCOLS[2], WSSProtocol)

    def test_get_protocol_found(self) -> None:
        for key in ("reality", "xhttp", "wss"):
            p = get_protocol(key)
            assert p is not None
            assert p.key == key

    def test_get_protocol_not_found(self) -> None:
        assert get_protocol("nonexistent") is None
        assert get_protocol("") is None

    def test_protocol_keys_unique(self) -> None:
        keys = [p.key for p in PROTOCOLS]
        assert len(keys) == len(set(keys))

    def test_protocol_references_inbound_types(self) -> None:
        """Each protocol's inbound_type must be the same object from INBOUND_TYPES."""
        for p in PROTOCOLS:
            assert p.inbound_type is INBOUND_TYPES[p.key]

    def test_remark_and_email_prefix_convenience(self) -> None:
        """Convenience properties must match the inbound_type."""
        for p in PROTOCOLS:
            assert p.remark == p.inbound_type.remark
            assert p.email_prefix == p.inbound_type.email_prefix


# ---------------------------------------------------------------------------
# Protocol.build_url()
# ---------------------------------------------------------------------------


class TestRealityBuildURL:
    def test_basic_url(self) -> None:
        proto = RealityProtocol()
        url = proto.build_url(
            "test-uuid",
            "alice",
            ip="1.2.3.4",
            sni="www.microsoft.com",
            public_key="myPBK",
            short_id="abc123",
        )
        assert url.startswith("vless://test-uuid@1.2.3.4:443")
        assert "flow=xtls-rprx-vision" in url
        assert "security=reality" in url
        assert "sni=www.microsoft.com" in url
        assert "fp=chrome" in url
        assert "pbk=myPBK" in url
        assert "sid=abc123" in url
        assert "type=tcp" in url
        assert "headerType=none" in url
        assert url.endswith("#alice")

    def test_custom_fingerprint(self) -> None:
        proto = RealityProtocol()
        url = proto.build_url("uuid", "name", ip="1.2.3.4", fingerprint="firefox")
        assert "fp=firefox" in url

    def test_default_sni(self) -> None:
        proto = RealityProtocol()
        url = proto.build_url("uuid", "name", ip="1.2.3.4")
        assert "sni=www.microsoft.com" in url

    def test_different_sni(self) -> None:
        proto = RealityProtocol()
        url = proto.build_url("uuid", "name", ip="5.6.7.8", sni="dl.google.com")
        assert "sni=dl.google.com" in url


class TestXHTTPBuildURL:
    def test_basic_url(self) -> None:
        proto = XHTTPProtocol()
        url = proto.build_url(
            "test-uuid",
            "bob",
            ip="1.2.3.4",
            port=12345,
            sni="www.microsoft.com",
            public_key="myPBK",
            short_id="abc123",
        )
        assert url.startswith("vless://test-uuid@1.2.3.4:12345")
        assert "security=reality" in url
        assert "type=xhttp" in url
        assert "mode=packet-up" in url
        assert "path=%2F" in url
        assert url.endswith("#bob-XHTTP")
        # XHTTP must NOT have flow parameter
        assert "flow=" not in url

    def test_url_suffix(self) -> None:
        assert XHTTPProtocol().url_suffix == "-XHTTP"

    def test_shares_uuid_with_reality(self) -> None:
        assert XHTTPProtocol().shares_uuid_with == "reality"


class TestWSSBuildURL:
    def test_basic_url(self) -> None:
        proto = WSSProtocol()
        url = proto.build_url(
            "wss-uuid",
            "carol",
            domain="example.com",
            ws_path="ws789",
        )
        assert url.startswith("vless://wss-uuid@example.com:443")
        assert "security=tls" in url
        assert "sni=example.com" in url
        assert "type=ws" in url
        assert "host=example.com" in url
        assert "path=%2Fws789" in url
        assert url.endswith("#carol-WSS")

    def test_url_suffix(self) -> None:
        assert WSSProtocol().url_suffix == "-WSS"

    def test_requires_domain(self) -> None:
        assert WSSProtocol().requires_domain is True

    def test_reality_does_not_require_domain(self) -> None:
        assert RealityProtocol().requires_domain is False

    def test_xhttp_does_not_require_domain(self) -> None:
        assert XHTTPProtocol().requires_domain is False

    def test_wss_own_uuid(self) -> None:
        """WSS uses its own UUID (no shares_uuid_with)."""
        assert WSSProtocol().shares_uuid_with is None


# ---------------------------------------------------------------------------
# Protocol.client_settings()
# ---------------------------------------------------------------------------


class TestClientSettings:
    def test_reality_client_settings(self) -> None:
        proto = RealityProtocol()
        settings = proto.client_settings("my-uuid", "reality-alice")
        clients = settings["clients"]
        assert len(clients) == 1
        c = clients[0]
        assert c["id"] == "my-uuid"
        assert c["flow"] == "xtls-rprx-vision"
        assert c["email"] == "reality-alice"
        assert c["enable"] is True
        assert c["limitIp"] == 2

    def test_xhttp_client_settings(self) -> None:
        proto = XHTTPProtocol()
        settings = proto.client_settings("my-uuid", "xhttp-alice")
        c = settings["clients"][0]
        assert c["id"] == "my-uuid"
        assert c["flow"] == ""  # XHTTP has no flow
        assert c["email"] == "xhttp-alice"

    def test_wss_client_settings(self) -> None:
        proto = WSSProtocol()
        settings = proto.client_settings("wss-uuid", "wss-alice")
        c = settings["clients"][0]
        assert c["id"] == "wss-uuid"
        assert c["flow"] == ""  # WSS has no flow
        assert c["email"] == "wss-alice"

    def test_all_settings_have_required_fields(self) -> None:
        """All protocols must produce settings with the required 3x-ui fields."""
        required_keys = {"id", "flow", "email", "limitIp", "totalGB", "expiryTime", "enable"}
        for proto in PROTOCOLS:
            settings = proto.client_settings("uuid", "email")
            c = settings["clients"][0]
            assert required_keys.issubset(c.keys()), f"{proto.key} missing fields"


# ---------------------------------------------------------------------------
# Protocol.find_inbound()
# ---------------------------------------------------------------------------


def _make_inbound(remark: str, port: int = 443) -> Inbound:
    return Inbound(id=1, remark=remark, protocol="vless", port=port)


class TestFindInbound:
    def test_finds_matching_inbound(self) -> None:
        inbounds = [
            _make_inbound("VLESS-Reality"),
            _make_inbound("VLESS-WSS"),
        ]
        proto = RealityProtocol()
        ib = proto.find_inbound(inbounds)
        assert ib is not None
        assert ib.remark == "VLESS-Reality"

    def test_returns_none_when_missing(self) -> None:
        inbounds = [_make_inbound("VLESS-WSS")]
        proto = RealityProtocol()
        assert proto.find_inbound(inbounds) is None

    def test_returns_none_for_empty_list(self) -> None:
        for proto in PROTOCOLS:
            assert proto.find_inbound([]) is None


# ---------------------------------------------------------------------------
# available_protocols()
# ---------------------------------------------------------------------------


class TestAvailableProtocols:
    def test_all_available(self) -> None:
        inbounds = [
            _make_inbound("VLESS-Reality"),
            _make_inbound("VLESS-Reality-XHTTP", port=12345),
            _make_inbound("VLESS-WSS"),
        ]
        result = available_protocols(inbounds, domain="example.com")
        keys = [p.key for p in result]
        assert keys == ["reality", "xhttp", "wss"]

    def test_reality_only(self) -> None:
        inbounds = [_make_inbound("VLESS-Reality")]
        result = available_protocols(inbounds)
        assert len(result) == 1
        assert result[0].key == "reality"

    def test_wss_excluded_without_domain(self) -> None:
        inbounds = [
            _make_inbound("VLESS-Reality"),
            _make_inbound("VLESS-WSS"),
        ]
        result = available_protocols(inbounds, domain="")
        keys = [p.key for p in result]
        assert "wss" not in keys
        assert "reality" in keys

    def test_wss_included_with_domain(self) -> None:
        inbounds = [
            _make_inbound("VLESS-Reality"),
            _make_inbound("VLESS-WSS"),
        ]
        result = available_protocols(inbounds, domain="example.com")
        keys = [p.key for p in result]
        assert "wss" in keys

    def test_empty_inbounds(self) -> None:
        result = available_protocols([])
        assert result == []

    def test_unknown_inbound_ignored(self) -> None:
        inbounds = [
            _make_inbound("VLESS-Reality"),
            _make_inbound("Something-Else"),
        ]
        result = available_protocols(inbounds)
        assert len(result) == 1
        assert result[0].key == "reality"

    def test_preserves_protocol_order(self) -> None:
        """Even if inbounds are in different order, result follows PROTOCOLS order."""
        inbounds = [
            _make_inbound("VLESS-WSS"),
            _make_inbound("VLESS-Reality-XHTTP", port=9999),
            _make_inbound("VLESS-Reality"),
        ]
        result = available_protocols(inbounds, domain="example.com")
        keys = [p.key for p in result]
        assert keys == ["reality", "xhttp", "wss"]
