"""Tests for Remnawave API client — finders, SDK converters, retry, auth.

SDK-backed methods are tested by mocking the converter inputs.
Raw-httpx methods (config profiles, squads) are tested with mocked httpx.Client.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from meridian.remnawave import (
    ConfigProfile,
    Host,
    MeridianPanel,
    Node,
    RemnawaveAuthError,
    RemnawaveError,
    RemnawaveNetworkError,
    RemnawaveNotFoundError,
    _host_from_sdk,
    _inbound_from_sdk,
    _node_from_sdk,
    _user_from_sdk,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data: dict | list | None = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = ""
    resp.content = b""
    resp.raise_for_status = MagicMock()
    return resp


def _make_panel(mock_client: MagicMock | None = None) -> MeridianPanel:
    """Create a MeridianPanel with a mocked httpx.Client and SDK bypassed."""
    client = mock_client or MagicMock()
    panel = MeridianPanel.__new__(MeridianPanel)
    panel._base = "https://198.51.100.1/panel"
    panel._token = "test-token"
    panel._timeout = 30
    panel._max_retries = 3
    panel._client = client
    panel._sdk = MagicMock()
    return panel


def _ns(**kwargs: object) -> SimpleNamespace:
    """Create a SimpleNamespace for mocking SDK response objects."""
    return SimpleNamespace(**kwargs)


# ---------------------------------------------------------------------------
# Finder Methods
# ---------------------------------------------------------------------------


class TestFindNodeByAddress:
    def test_returns_matching_node(self) -> None:
        panel = _make_panel()
        panel.list_nodes = MagicMock(
            return_value=[
                Node(uuid="uuid-1", address="198.51.100.1"),
                Node(uuid="uuid-2", address="198.51.100.2"),
            ]
        )
        result = panel.find_node_by_address("198.51.100.2")
        assert result is not None
        assert result.uuid == "uuid-2"

    def test_returns_none_when_not_found(self) -> None:
        panel = _make_panel()
        panel.list_nodes = MagicMock(return_value=[Node(uuid="uuid-1", address="198.51.100.1")])
        assert panel.find_node_by_address("198.51.100.99") is None

    def test_returns_none_on_empty_list(self) -> None:
        panel = _make_panel()
        panel.list_nodes = MagicMock(return_value=[])
        assert panel.find_node_by_address("198.51.100.1") is None


class TestFindHostByRemark:
    def test_returns_matching_host(self) -> None:
        panel = _make_panel()
        panel.list_hosts = MagicMock(
            return_value=[
                Host(uuid="h1", remark="reality-198.51.100.1"),
                Host(uuid="h2", remark="xhttp-198.51.100.1"),
            ]
        )
        result = panel.find_host_by_remark("xhttp-198.51.100.1")
        assert result is not None
        assert result.uuid == "h2"

    def test_returns_none_when_not_found(self) -> None:
        panel = _make_panel()
        panel.list_hosts = MagicMock(return_value=[Host(uuid="h1", remark="reality-198.51.100.1")])
        assert panel.find_host_by_remark("wss-example.com") is None

    def test_returns_none_on_empty_list(self) -> None:
        panel = _make_panel()
        panel.list_hosts = MagicMock(return_value=[])
        assert panel.find_host_by_remark("reality-198.51.100.1") is None


class TestFindConfigProfileByName:
    def test_returns_matching_profile(self) -> None:
        panel = _make_panel()
        panel.list_config_profiles = MagicMock(
            return_value=[
                ConfigProfile(uuid="cp-1", name="meridian-default"),
                ConfigProfile(uuid="cp-2", name="other"),
            ]
        )
        result = panel.find_config_profile_by_name("meridian-default")
        assert result is not None
        assert result.uuid == "cp-1"

    def test_returns_none_when_not_found(self) -> None:
        panel = _make_panel()
        panel.list_config_profiles = MagicMock(return_value=[ConfigProfile(uuid="cp-1", name="meridian-default")])
        assert panel.find_config_profile_by_name("nonexistent") is None

    def test_returns_none_on_empty_list(self) -> None:
        panel = _make_panel()
        panel.list_config_profiles = MagicMock(return_value=[])
        assert panel.find_config_profile_by_name("meridian-default") is None


# ---------------------------------------------------------------------------
# SDK → Dataclass Converters
# ---------------------------------------------------------------------------


class TestUserFromSdk:
    def test_converts_all_fields(self) -> None:
        obj = _ns(
            uuid="u-1",
            shortUuid="abc",
            username="alice",
            vlessUuid="vl-1",
            status="ACTIVE",
            usedTrafficBytes=1024,
            trafficLimitBytes=2048,
            createdAt="2026-01-01",
            onlineAt="2026-04-01",
            subRevokedAt="",
        )
        user = _user_from_sdk(obj)
        assert user.uuid == "u-1"
        assert user.short_uuid == "abc"
        assert user.username == "alice"
        assert user.status == "ACTIVE"
        assert user.used_traffic_bytes == 1024
        assert user.traffic_limit_bytes == 2048
        assert user.online_at == "2026-04-01"

    def test_handles_missing_fields(self) -> None:
        user = _user_from_sdk(_ns(uuid="u-1"))
        assert user.uuid == "u-1"
        assert user.username == ""
        assert user.used_traffic_bytes == 0

    def test_handles_none_traffic(self) -> None:
        user = _user_from_sdk(_ns(usedTrafficBytes=None, trafficLimitBytes=None))
        assert user.used_traffic_bytes == 0
        assert user.traffic_limit_bytes == 0


class TestNodeFromSdk:
    def test_converts_all_fields(self) -> None:
        obj = _ns(
            uuid="n-1",
            name="finland",
            address="198.51.100.1",
            port=3010,
            isConnected=True,
            isDisabled=False,
            xrayVersion="26.2.6",
            trafficUsedBytes=5000,
        )
        node = _node_from_sdk(obj)
        assert node.uuid == "n-1"
        assert node.name == "finland"
        assert node.address == "198.51.100.1"
        assert node.port == 3010
        assert node.is_connected is True
        assert node.traffic_used == 5000

    def test_handles_missing_fields(self) -> None:
        node = _node_from_sdk(_ns())
        assert node.uuid == ""
        assert node.is_connected is False


class TestHostFromSdk:
    def test_converts_all_fields(self) -> None:
        obj = _ns(
            uuid="h-1",
            remark="reality-198.51.100.1",
            address="198.51.100.1",
            port=443,
            sni="www.google.com",
            inboundUuid="ib-1",
            isDisabled=False,
        )
        host = _host_from_sdk(obj)
        assert host.uuid == "h-1"
        assert host.remark == "reality-198.51.100.1"
        assert host.sni == "www.google.com"
        assert host.inbound_uuid == "ib-1"

    def test_handles_missing_fields(self) -> None:
        host = _host_from_sdk(_ns())
        assert host.uuid == ""
        assert host.sni == ""


class TestInboundFromSdk:
    def test_converts_all_fields(self) -> None:
        obj = _ns(uuid="ib-1", tag="vless-reality", type="vless", network="tcp", security="reality")
        ib = _inbound_from_sdk(obj)
        assert ib.uuid == "ib-1"
        assert ib.tag == "vless-reality"
        assert ib.type == "vless"
        assert ib.security == "reality"

    def test_handles_empty(self) -> None:
        ib = _inbound_from_sdk(_ns())
        assert ib.uuid == ""
        assert ib.tag == ""


# ---------------------------------------------------------------------------
# Retry Logic (raw httpx path — used by config profiles, squads)
# ---------------------------------------------------------------------------


class TestRetryLogic:
    def test_retries_on_500_error(self) -> None:
        mock_client = MagicMock()
        resp_500 = _mock_response(500, {"error": "internal"})
        resp_200 = _mock_response(200, {"response": {"ok": True}})
        mock_client.request.side_effect = [resp_500, resp_200]
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/test")
        assert result == {"ok": True}
        assert mock_client.request.call_count == 2

    def test_no_retry_on_401(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(401)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveError, match="401"):
            panel._request("GET", "/api/test")
        assert mock_client.request.call_count == 1

    def test_no_retry_on_403(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(403)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveError, match="403"):
            panel._request("GET", "/api/test")
        assert mock_client.request.call_count == 1

    def test_retries_on_connect_error(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.request.side_effect = [
            httpx.ConnectError("refused"),
            _mock_response(200, {"response": "ok"}),
        ]
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/test")
        assert result == "ok"

    def test_retries_on_timeout(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.request.side_effect = [
            httpx.ReadTimeout("slow"),
            _mock_response(200, {"response": "ok"}),
        ]
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/test")
        assert result == "ok"

    def test_max_retries_exceeded_raises(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.request.side_effect = httpx.ConnectError("down")
        panel = _make_panel(mock_client)
        panel._max_retries = 2
        with pytest.raises(RemnawaveError, match="Cannot connect"):
            panel._request("GET", "/api/test")
        assert mock_client.request.call_count == 2

    def test_unwraps_response_wrapper(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(200, {"response": {"users": [{"uuid": "u-1"}]}})
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/users")
        assert result == {"users": [{"uuid": "u-1"}]}

    def test_passes_through_non_wrapped(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(200, [{"uuid": "u-1"}])
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/users")
        assert result == [{"uuid": "u-1"}]


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------


class TestPing:
    def test_ping_returns_true_on_success(self) -> None:
        panel = _make_panel()
        # Mock the SDK users call used by ping
        panel.ping = MagicMock(return_value=True)
        assert panel.ping() is True

    def test_ping_returns_false_on_error(self) -> None:
        panel = _make_panel()
        panel.ping = MagicMock(return_value=False)
        assert panel.ping() is False


# ---------------------------------------------------------------------------
# Context Manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_closes_on_exit(self) -> None:
        mock_client = MagicMock()
        panel = _make_panel(mock_client)
        with panel:
            pass
        mock_client.close.assert_called_once()

    def test_usable_as_context_manager(self) -> None:
        panel = _make_panel()
        panel.ping = MagicMock(return_value=True)
        with panel:
            assert panel.ping() is True


# ---------------------------------------------------------------------------
# Auth Methods
# ---------------------------------------------------------------------------


class TestAuth:
    def test_login_returns_token(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": {"accessToken": "jwt-123"}}

        with patch("httpx.post", return_value=mock_resp):
            token = MeridianPanel.login("https://198.51.100.1", "admin", "pass")

        assert token == "jwt-123"

    def test_login_fails_on_non_200(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(RemnawaveError, match="login failed"):
                MeridianPanel.login("https://198.51.100.1", "admin", "wrong")

    def test_register_admin_returns_token(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"response": {"accessToken": "jwt-456"}}

        with patch("httpx.post", return_value=mock_resp):
            token = MeridianPanel.register_admin("https://198.51.100.1", "admin", "pass")

        assert token == "jwt-456"

    def test_register_admin_accepts_200(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": {"token": "jwt-789"}}

        with patch("httpx.post", return_value=mock_resp):
            token = MeridianPanel.register_admin("https://198.51.100.1", "admin", "pass")

        assert token == "jwt-789"

    def test_login_no_token_in_response(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": {}}

        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(RemnawaveError, match="no token"):
                MeridianPanel.login("https://198.51.100.1", "admin", "pass")


# ---------------------------------------------------------------------------
# Config Profiles (raw httpx path)
# ---------------------------------------------------------------------------


class TestConfigProfiles:
    def test_create_config_profile(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(return_value={"uuid": "cp-1", "name": "meridian-default"})
        profile = panel.create_config_profile("meridian-default", {"inbounds": []})
        assert profile.uuid == "cp-1"
        assert profile.name == "meridian-default"

    def test_get_config_profile_found(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value={"uuid": "cp-1", "name": "test"})
        profile = panel.get_config_profile("cp-1")
        assert profile is not None
        assert profile.name == "test"

    def test_get_config_profile_not_found(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNotFoundError("404"))
        assert panel.get_config_profile("nonexistent") is None

    def test_list_config_profiles(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(
            return_value=[
                {"uuid": "cp-1", "name": "default"},
                {"uuid": "cp-2", "name": "other"},
            ]
        )
        profiles = panel.list_config_profiles()
        assert len(profiles) == 2


# ---------------------------------------------------------------------------
# Internal Squads (raw httpx path)
# ---------------------------------------------------------------------------


class TestInternalSquads:
    def test_list_internal_squads(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value={"internalSquads": [{"uuid": "sq-1", "name": "Default-Squad"}]})
        squads = panel.list_internal_squads()
        assert len(squads) == 1
        assert squads[0]["name"] == "Default-Squad"

    def test_get_default_squad_uuid(self) -> None:
        panel = _make_panel()
        panel.list_internal_squads = MagicMock(return_value=[{"uuid": "sq-1", "name": "Default-Squad"}])
        assert panel.get_default_squad_uuid() == "sq-1"

    def test_get_default_squad_uuid_not_found(self) -> None:
        panel = _make_panel()
        panel.list_internal_squads = MagicMock(return_value=[{"uuid": "sq-1", "name": "Other"}])
        assert panel.get_default_squad_uuid() == ""


# ---------------------------------------------------------------------------
# Error Subclasses & Safety
# ---------------------------------------------------------------------------


class TestErrorSubclasses:
    def test_not_found_is_remnawave_error(self) -> None:
        assert issubclass(RemnawaveNotFoundError, RemnawaveError)

    def test_auth_is_remnawave_error(self) -> None:
        assert issubclass(RemnawaveAuthError, RemnawaveError)

    def test_network_is_remnawave_error(self) -> None:
        assert issubclass(RemnawaveNetworkError, RemnawaveError)

    def test_404_raises_not_found(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(404)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveNotFoundError):
            panel._request("GET", "/api/test")

    def test_401_raises_auth_error(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(401)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveAuthError):
            panel._request("GET", "/api/test")

    def test_403_raises_auth_error(self) -> None:
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(403)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveAuthError):
            panel._request("GET", "/api/test")

    def test_connect_error_raises_network_error(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.request.side_effect = httpx.ConnectError("refused")
        panel = _make_panel(mock_client)
        panel._max_retries = 1
        with pytest.raises(RemnawaveNetworkError):
            panel._request("GET", "/api/test")

    def test_timeout_raises_network_error(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.request.side_effect = httpx.ReadTimeout("slow")
        panel = _make_panel(mock_client)
        panel._max_retries = 1
        with pytest.raises(RemnawaveNetworkError):
            panel._request("GET", "/api/test")

    def test_json_decode_error_raises_remnawave_error(self) -> None:
        mock_client = MagicMock()
        resp = _mock_response(200)
        resp.json.side_effect = ValueError("Expecting value")
        resp.content = b"<html>truncated"
        mock_client.request.return_value = resp
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveError, match="invalid JSON"):
            panel._request("GET", "/api/test")


class TestGetMethodErrorPropagation:
    def test_get_config_profile_not_found_returns_none(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNotFoundError("404"))
        assert panel.get_config_profile("cp-1") is None

    def test_get_config_profile_auth_error_propagates(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveAuthError("expired"))
        with pytest.raises(RemnawaveAuthError):
            panel.get_config_profile("cp-1")
