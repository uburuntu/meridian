"""Tests for Remnawave API client — finders, parsing, retry, auth.

Uses MagicMock for httpx.Client injection. No real HTTP calls.
"""

from __future__ import annotations

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
    _parse_host,
    _parse_inbound,
    _parse_node,
    _parse_user,
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
    """Create a MeridianPanel with a mocked httpx.Client.

    httpx is imported locally inside __init__, so we patch it at the
    call site within the method body.
    """
    client = mock_client or MagicMock()
    with patch.dict("sys.modules", {"httpx": MagicMock()}):
        panel = MeridianPanel.__new__(MeridianPanel)
    panel._base = "https://198.51.100.1/panel"
    panel._token = "test-token"
    panel._timeout = 30
    panel._max_retries = 3
    panel._client = client
    return panel


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
# Response Parsing
# ---------------------------------------------------------------------------


class TestParseUser:
    def test_parses_camelcase_fields(self) -> None:
        user = _parse_user(
            {
                "uuid": "u-1",
                "shortUuid": "abc",
                "username": "alice",
                "status": "ACTIVE",
                "usedTrafficBytes": 1024,
                "trafficLimitBytes": 2048,
                "createdAt": "2026-01-01",
                "onlineAt": "2026-04-01",
            }
        )
        assert user.uuid == "u-1"
        assert user.short_uuid == "abc"
        assert user.username == "alice"
        assert user.status == "ACTIVE"
        assert user.used_traffic_bytes == 1024
        assert user.traffic_limit_bytes == 2048
        assert user.online_at == "2026-04-01"

    def test_handles_missing_fields(self) -> None:
        user = _parse_user({"uuid": "u-1"})
        assert user.uuid == "u-1"
        assert user.username == ""
        assert user.used_traffic_bytes == 0

    def test_handles_non_dict(self) -> None:
        user = _parse_user(None)
        assert user.uuid == ""

    def test_handles_none_traffic(self) -> None:
        """None traffic values should become 0."""
        user = _parse_user({"usedTrafficBytes": None, "trafficLimitBytes": None})
        assert user.used_traffic_bytes == 0
        assert user.traffic_limit_bytes == 0

    def test_preserves_raw_data(self) -> None:
        data = {"uuid": "u-1", "customField": "custom"}
        user = _parse_user(data)
        assert user._raw == data

    def test_snake_case_fallback(self) -> None:
        """short_uuid fallback for APIs that use snake_case."""
        user = _parse_user({"short_uuid": "xyz"})
        assert user.short_uuid == "xyz"


class TestParseNode:
    def test_parses_all_fields(self) -> None:
        node = _parse_node(
            {
                "uuid": "n-1",
                "name": "finland",
                "address": "198.51.100.1",
                "port": 3010,
                "isConnected": True,
                "isDisabled": False,
                "xrayVersion": "26.2.6",
                "trafficUsed": 5000,
            }
        )
        assert node.uuid == "n-1"
        assert node.name == "finland"
        assert node.address == "198.51.100.1"
        assert node.port == 3010
        assert node.is_connected is True
        assert node.traffic_used == 5000

    def test_handles_missing_fields(self) -> None:
        node = _parse_node({})
        assert node.uuid == ""
        assert node.is_connected is False

    def test_handles_non_dict(self) -> None:
        node = _parse_node("not a dict")
        assert node.uuid == ""


class TestParseHost:
    def test_parses_all_fields(self) -> None:
        host = _parse_host(
            {
                "uuid": "h-1",
                "remark": "reality-198.51.100.1",
                "address": "198.51.100.1",
                "port": 443,
                "sni": "www.google.com",
                "inboundUuid": "ib-1",
                "isDisabled": False,
            }
        )
        assert host.uuid == "h-1"
        assert host.remark == "reality-198.51.100.1"
        assert host.sni == "www.google.com"
        assert host.inbound_uuid == "ib-1"

    def test_snake_case_inbound_uuid_fallback(self) -> None:
        host = _parse_host({"inbound_uuid": "ib-2"})
        assert host.inbound_uuid == "ib-2"

    def test_handles_non_dict(self) -> None:
        host = _parse_host([])
        assert host.uuid == ""


class TestParseInbound:
    def test_parses_all_fields(self) -> None:
        ib = _parse_inbound(
            {
                "uuid": "ib-1",
                "tag": "vless-reality",
                "type": "vless",
                "network": "tcp",
                "security": "reality",
            }
        )
        assert ib.uuid == "ib-1"
        assert ib.tag == "vless-reality"
        assert ib.type == "vless"
        assert ib.security == "reality"

    def test_handles_empty_dict(self) -> None:
        ib = _parse_inbound({})
        assert ib.uuid == ""
        assert ib.tag == ""


# ---------------------------------------------------------------------------
# Retry Logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    def test_retries_on_500_error(self) -> None:
        """Server errors should be retried with backoff."""
        mock_client = MagicMock()
        resp_500 = _mock_response(500, {"error": "internal"})
        resp_500.raise_for_status = MagicMock()  # Don't raise on 500 (handled by code)
        resp_200 = _mock_response(200, {"response": {"ok": True}})

        mock_client.request.side_effect = [resp_500, resp_200]
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/test")
        assert result == {"ok": True}
        assert mock_client.request.call_count == 2

    def test_no_retry_on_401(self) -> None:
        """Auth errors should fail immediately."""
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(401)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveError, match="401"):
            panel._request("GET", "/api/test")
        assert mock_client.request.call_count == 1

    def test_no_retry_on_403(self) -> None:
        """Permission errors should fail immediately."""
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(403)
        panel = _make_panel(mock_client)
        with pytest.raises(RemnawaveError, match="403"):
            panel._request("GET", "/api/test")
        assert mock_client.request.call_count == 1

    def test_retries_on_connect_error(self) -> None:
        """Connection errors should be retried."""
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
        """Timeout errors should be retried."""
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
        """After exhausting retries, should raise."""
        import httpx

        mock_client = MagicMock()
        mock_client.request.side_effect = httpx.ConnectError("down")
        panel = _make_panel(mock_client)
        panel._max_retries = 2
        with pytest.raises(RemnawaveError, match="Cannot connect"):
            panel._request("GET", "/api/test")
        assert mock_client.request.call_count == 2

    def test_unwraps_response_wrapper(self) -> None:
        """Remnawave wraps responses in {"response": ...}."""
        mock_client = MagicMock()
        mock_client.request.return_value = _mock_response(200, {"response": {"users": [{"uuid": "u-1"}]}})
        panel = _make_panel(mock_client)
        result = panel._request("GET", "/api/users")
        assert result == {"users": [{"uuid": "u-1"}]}

    def test_passes_through_non_wrapped(self) -> None:
        """Non-wrapped responses should be returned as-is."""
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
        panel._get = MagicMock(return_value=[])
        assert panel.ping() is True

    def test_ping_returns_false_on_error(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveError("down"))
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
        panel._get = MagicMock(return_value=[])
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
# API Methods
# ---------------------------------------------------------------------------


class TestCreateUser:
    def test_create_user_calls_api(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(
            return_value={"uuid": "u-1", "shortUuid": "abc", "username": "alice", "status": "ACTIVE"}
        )
        user = panel.create_user("alice")
        assert user.uuid == "u-1"
        assert user.username == "alice"
        panel._post.assert_called_once()
        call_args = panel._post.call_args
        assert call_args[0][0] == "/api/users"
        assert call_args[1]["json"]["username"] == "alice"
        assert call_args[1]["json"]["expireAt"] == "2099-12-31T23:59:59.000Z"

    def test_create_user_with_traffic_limit(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(return_value={"uuid": "u-1", "username": "bob"})
        panel.create_user("bob", traffic_limit_bytes=1073741824)
        call_json = panel._post.call_args[1]["json"]
        assert call_json["trafficLimitBytes"] == 1073741824


class TestListUsers:
    def test_list_users_flat_response(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value=[{"uuid": "u-1"}, {"uuid": "u-2"}])
        users = panel.list_users()
        assert len(users) == 2

    def test_list_users_paginated_response(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value={"users": [{"uuid": "u-1"}]})
        users = panel.list_users()
        assert len(users) == 1

    def test_list_users_empty(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value=[])
        assert panel.list_users() == []


class TestGetUser:
    def test_get_user_found(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value={"uuid": "u-1", "username": "alice"})
        user = panel.get_user("alice")
        assert user is not None
        assert user.username == "alice"

    def test_get_user_not_found(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNotFoundError("404"))
        assert panel.get_user("nobody") is None


class TestDeleteUser:
    def test_delete_success(self) -> None:
        panel = _make_panel()
        panel._delete = MagicMock(return_value=None)
        assert panel.delete_user("u-1") is True

    def test_delete_failure(self) -> None:
        panel = _make_panel()
        panel._delete = MagicMock(side_effect=RemnawaveNotFoundError("not found"))
        assert panel.delete_user("u-1") is False


class TestCreateNode:
    def test_create_node_returns_credentials(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(return_value={"uuid": "n-1"})
        panel._get = MagicMock(return_value={"pubKey": "secret-key-data"})
        creds = panel.create_node("node-1", "198.51.100.1", 3010)
        assert creds.uuid == "n-1"
        assert creds.secret_key == "secret-key-data"

    def test_create_node_with_config_profile(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(return_value={"uuid": "n-2"})
        panel._get = MagicMock(return_value={})
        panel.create_node(
            "node-2",
            "198.51.100.2",
            3010,
            config_profile_uuid="cp-1",
            inbound_uuids=["ib-1", "ib-2"],
        )
        call_json = panel._post.call_args[1]["json"]
        assert call_json["configProfile"]["activeConfigProfileUuid"] == "cp-1"
        assert call_json["configProfile"]["activeInbounds"] == ["ib-1", "ib-2"]


class TestCreateHost:
    def test_create_host_minimal(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(return_value={"uuid": "h-1", "remark": "reality-198.51.100.1", "port": 443})
        host = panel.create_host(
            remark="reality-198.51.100.1",
            address="198.51.100.1",
            port=443,
            config_profile_uuid="cp-1",
            inbound_uuid="ib-1",
        )
        assert host.uuid == "h-1"
        call_json = panel._post.call_args[1]["json"]
        assert call_json["inbound"]["configProfileUuid"] == "cp-1"
        assert call_json["inbound"]["configProfileInboundUuid"] == "ib-1"

    def test_create_host_with_optional_fields(self) -> None:
        panel = _make_panel()
        panel._post = MagicMock(return_value={"uuid": "h-2"})
        panel.create_host(
            remark="reality-198.51.100.1",
            address="198.51.100.1",
            port=443,
            config_profile_uuid="cp-1",
            inbound_uuid="ib-1",
            sni="www.google.com",
            fingerprint="chrome",
            security_layer="TLS",
            is_disabled=True,
        )
        call_json = panel._post.call_args[1]["json"]
        assert call_json["sni"] == "www.google.com"
        assert call_json["fingerprint"] == "chrome"
        assert call_json["securityLayer"] == "TLS"
        assert call_json["isDisabled"] is True


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


class TestListInbounds:
    def test_list_inbounds_wrapped(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value={"inbounds": [{"uuid": "ib-1", "tag": "vless-reality"}]})
        inbounds = panel.list_inbounds()
        assert len(inbounds) == 1
        assert inbounds[0].tag == "vless-reality"

    def test_list_inbounds_flat(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value=[{"uuid": "ib-1"}])
        assert len(panel.list_inbounds()) == 1

    def test_list_inbounds_empty(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(return_value={})
        assert panel.list_inbounds() == []


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
    def test_get_user_not_found_returns_none(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNotFoundError("404"))
        assert panel.get_user("nobody") is None

    def test_get_user_network_error_propagates(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNetworkError("timeout"))
        with pytest.raises(RemnawaveNetworkError):
            panel.get_user("alice")

    def test_get_user_auth_error_propagates(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveAuthError("expired"))
        with pytest.raises(RemnawaveAuthError):
            panel.get_user("alice")

    def test_get_node_not_found_returns_none(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNotFoundError("404"))
        assert panel.get_node("uuid-1") is None

    def test_get_node_network_error_propagates(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNetworkError("down"))
        with pytest.raises(RemnawaveNetworkError):
            panel.get_node("uuid-1")

    def test_get_config_profile_not_found_returns_none(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveNotFoundError("404"))
        assert panel.get_config_profile("cp-1") is None

    def test_get_config_profile_auth_error_propagates(self) -> None:
        panel = _make_panel()
        panel._get = MagicMock(side_effect=RemnawaveAuthError("expired"))
        with pytest.raises(RemnawaveAuthError):
            panel.get_config_profile("cp-1")

    def test_delete_user_not_found_returns_false(self) -> None:
        panel = _make_panel()
        panel._delete = MagicMock(side_effect=RemnawaveNotFoundError("gone"))
        assert panel.delete_user("uuid-1") is False

    def test_delete_user_network_error_propagates(self) -> None:
        panel = _make_panel()
        panel._delete = MagicMock(side_effect=RemnawaveNetworkError("timeout"))
        with pytest.raises(RemnawaveNetworkError):
            panel.delete_user("uuid-1")
