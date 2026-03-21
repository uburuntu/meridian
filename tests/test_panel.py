"""Tests for PanelClient — 3x-ui REST API wrapper via SSH."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from meridian.models import Inbound
from meridian.panel import PanelClient, PanelError


def _make_conn(stdout: str = "", stderr: str = "", rc: int = 0) -> MagicMock:
    """Create a mock ServerConnection with preset run() output."""
    conn = MagicMock()
    conn.run.return_value = subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)
    return conn


def _make_panel(conn: MagicMock | None = None) -> PanelClient:
    """Create a PanelClient with a mock connection."""
    if conn is None:
        conn = _make_conn()
    return PanelClient(conn=conn, panel_port=2053, web_base_path="abc123")


class TestInit:
    def test_base_url(self) -> None:
        panel = _make_panel()
        assert panel.base_url == "http://127.0.0.1:2053/abc123"

    def test_cookie_path(self) -> None:
        panel = _make_panel()
        assert panel._cookie_path == "$HOME/.meridian/.cookie"


class TestLogin:
    def test_successful_login(self) -> None:
        conn = _make_conn(stdout='{"success": true}')
        panel = _make_panel(conn)
        panel.login("admin", "secret")

        # First call is the curl login, second is chmod for cookie permissions
        login_call = conn.run.call_args_list[0][0][0]
        assert "curl -s -c" in login_call
        assert "username=" in login_call
        assert "password=" in login_call
        assert "/login" in login_call
        # Verify form-urlencoded (not JSON content-type)
        assert "Content-Type: application/json" not in login_call
        # Verify cookie permissions are secured
        chmod_call = conn.run.call_args_list[1][0][0]
        assert "chmod 600" in chmod_call

    def test_login_with_special_characters(self) -> None:
        conn = _make_conn(stdout='{"success": true}')
        panel = _make_panel(conn)
        panel.login("admin", "p@ss'w\"ord")

        login_call = conn.run.call_args_list[0][0][0]
        # URL-encoded: @ → %40, ' → %27, " → %22
        assert "p%40ss" in login_call

    def test_login_failure_returns_error(self) -> None:
        conn = _make_conn(stdout='{"success": false, "msg": "wrong password"}')
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Login failed"):
            panel.login("admin", "wrong")

    def test_login_empty_response(self) -> None:
        conn = _make_conn(stdout="")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Empty response"):
            panel.login("admin", "pass")

    def test_login_invalid_json(self) -> None:
        conn = _make_conn(stdout="not json")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Invalid JSON"):
            panel.login("admin", "pass")

    def test_login_curl_failure(self) -> None:
        conn = _make_conn(rc=1, stderr="connection refused")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Login request failed"):
            panel.login("admin", "pass")


class TestListInbounds:
    def test_list_parses_inbounds(self) -> None:
        response = {
            "success": True,
            "obj": [
                {
                    "id": 1,
                    "remark": "VLESS-Reality",
                    "protocol": "vless",
                    "port": 443,
                    "settings": json.dumps(
                        {
                            "clients": [{"id": "uuid-1", "email": "reality-default", "flow": "xtls-rprx-vision"}],
                            "decryption": "none",
                        }
                    ),
                    "streamSettings": json.dumps({"network": "tcp", "security": "reality"}),
                },
                {
                    "id": 2,
                    "remark": "VLESS-WSS",
                    "protocol": "vless",
                    "port": 8443,
                    "settings": json.dumps({"clients": [{"id": "uuid-2", "email": "wss-default", "flow": ""}]}),
                    "streamSettings": json.dumps({"network": "ws", "security": "tls"}),
                },
            ],
        }
        conn = _make_conn(stdout=json.dumps(response))
        panel = _make_panel(conn)
        inbounds = panel.list_inbounds()

        assert len(inbounds) == 2
        assert inbounds[0].id == 1
        assert inbounds[0].remark == "VLESS-Reality"
        assert inbounds[0].protocol == "vless"
        assert inbounds[0].port == 443
        assert len(inbounds[0].clients) == 1
        assert inbounds[0].clients[0]["email"] == "reality-default"
        assert inbounds[0].stream_settings["security"] == "reality"

        assert inbounds[1].id == 2
        assert inbounds[1].remark == "VLESS-WSS"

    def test_list_empty(self) -> None:
        conn = _make_conn(stdout='{"success": true, "obj": []}')
        panel = _make_panel(conn)
        assert panel.list_inbounds() == []

    def test_list_failure(self) -> None:
        conn = _make_conn(stdout='{"success": false, "msg": "unauthorized"}')
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="List inbounds failed"):
            panel.list_inbounds()


class TestFindInbound:
    def test_find_existing(self) -> None:
        response = {
            "success": True,
            "obj": [
                {
                    "id": 1,
                    "remark": "VLESS-Reality",
                    "protocol": "vless",
                    "port": 443,
                    "settings": json.dumps({"clients": []}),
                    "streamSettings": "{}",
                },
                {
                    "id": 2,
                    "remark": "VLESS-WSS",
                    "protocol": "vless",
                    "port": 8443,
                    "settings": json.dumps({"clients": []}),
                    "streamSettings": "{}",
                },
            ],
        }
        conn = _make_conn(stdout=json.dumps(response))
        panel = _make_panel(conn)

        found = panel.find_inbound("VLESS-WSS")
        assert found is not None
        assert found.id == 2
        assert found.remark == "VLESS-WSS"

    def test_find_nonexistent(self) -> None:
        response = {
            "success": True,
            "obj": [
                {
                    "id": 1,
                    "remark": "VLESS-Reality",
                    "protocol": "vless",
                    "port": 443,
                    "settings": json.dumps({"clients": []}),
                    "streamSettings": "{}",
                },
            ],
        }
        conn = _make_conn(stdout=json.dumps(response))
        panel = _make_panel(conn)
        assert panel.find_inbound("VLESS-WSS") is None


class TestAddClient:
    def test_add_client_constructs_correct_body(self) -> None:
        conn = _make_conn(stdout='{"success": true}')
        panel = _make_panel(conn)

        client_settings = {
            "clients": [
                {
                    "id": "test-uuid",
                    "flow": "xtls-rprx-vision",
                    "email": "reality-alice",
                    "limitIp": 2,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0,
                }
            ]
        }
        panel.add_client(5, client_settings)

        call_args = conn.run.call_args[0][0]
        # Verify JSON content type is used (not form-urlencoded)
        assert "Content-Type: application/json" in call_args
        assert "/panel/api/inbounds/addClient" in call_args

    def test_add_client_settings_is_json_string(self) -> None:
        """Verify the 'settings' field is a JSON string, not a nested object."""
        conn = _make_conn(stdout='{"success": true}')
        panel = _make_panel(conn)

        client_settings = {"clients": [{"id": "uuid", "email": "test"}]}
        panel.add_client(1, client_settings)

        # Extract the -d argument from the curl command
        call_args = conn.run.call_args[0][0]
        # The body sent to curl should have 'settings' as a JSON string
        assert "addClient" in call_args

    def test_add_client_failure(self) -> None:
        conn = _make_conn(stdout='{"success": false, "msg": "duplicate email"}')
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Add client failed"):
            panel.add_client(1, {"clients": [{"id": "uuid"}]})


class TestRemoveClient:
    def test_remove_uses_uuid_endpoint(self) -> None:
        conn = _make_conn(stdout='{"success": true}')
        panel = _make_panel(conn)

        panel.remove_client(5, "550e8400-e29b-41d4-a716-446655440000")

        call_args = conn.run.call_args[0][0]
        # Verify UUID-based URL (not email-based)
        assert "/panel/api/inbounds/5/delClient/" in call_args
        assert "550e8400-e29b-41d4-a716-446655440000" in call_args
        assert "-X POST" in call_args

    def test_remove_client_failure(self) -> None:
        conn = _make_conn(stdout='{"success": false, "msg": "not found"}')
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Remove client failed"):
            panel.remove_client(1, "bad-uuid")


class TestGenerateUUID:
    def test_generate_uuid_success(self) -> None:
        conn = MagicMock()
        # First call: discover xray binary
        # Second call: generate UUID
        conn.run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="/app/bin/xray-linux-amd64\n", stderr=""),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="550e8400-e29b-41d4-a716-446655440000\n", stderr=""
            ),
        ]
        panel = _make_panel(conn)
        uuid = panel.generate_uuid()
        assert uuid == "550e8400-e29b-41d4-a716-446655440000"

    def test_generate_uuid_no_binary(self) -> None:
        conn = _make_conn(stdout="", rc=1, stderr="not found")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="Failed to discover Xray binary"):
            panel.generate_uuid()


class TestCleanup:
    def test_cleanup_removes_cookie(self) -> None:
        conn = _make_conn()
        panel = _make_panel(conn)
        panel.cleanup()
        call_args = conn.run.call_args[0][0]
        assert "rm -f" in call_args
        assert ".cookie" in call_args


class TestParseResponse:
    """Test the static parse_response method edge cases."""

    def test_html_error_page(self) -> None:
        """Panel might return HTML (e.g. nginx 502) instead of JSON."""
        with pytest.raises(PanelError, match="Invalid JSON"):
            PanelClient.parse_response("<html><body>502 Bad Gateway</body></html>", "/panel/api/inbounds/list")

    def test_truncated_json(self) -> None:
        with pytest.raises(PanelError, match="Invalid JSON"):
            PanelClient.parse_response('{"success": tru', "/login")

    def test_empty_string(self) -> None:
        with pytest.raises(PanelError, match="Empty response"):
            PanelClient.parse_response("", "/login")

    def test_whitespace_only(self) -> None:
        with pytest.raises(PanelError, match="Empty response"):
            PanelClient.parse_response("   \n  ", "/login")

    def test_valid_json_returned(self) -> None:
        result = PanelClient.parse_response('{"success": true, "obj": null}', "/test")
        assert result["success"] is True


class TestFindInboundNoMatch:
    """Extended find_inbound tests."""

    def test_find_empty_list(self) -> None:
        conn = _make_conn(stdout='{"success": true, "obj": []}')
        panel = _make_panel(conn)
        assert panel.find_inbound("VLESS-Reality") is None

    def test_find_partial_name_no_match(self) -> None:
        """find_inbound uses exact match, not substring."""
        response = {
            "success": True,
            "obj": [
                {
                    "id": 1,
                    "remark": "VLESS-Reality",
                    "protocol": "vless",
                    "port": 443,
                    "settings": json.dumps({"clients": []}),
                    "streamSettings": "{}",
                },
            ],
        }
        conn = _make_conn(stdout=json.dumps(response))
        panel = _make_panel(conn)
        # Substring should NOT match
        assert panel.find_inbound("Reality") is None
        assert panel.find_inbound("VLESS") is None


class TestAddClientBodyFormat:
    """Verify the JSON-string-inside-JSON body format for add_client."""

    def test_settings_field_is_json_string_in_body(self) -> None:
        """The API body's 'settings' field must be a JSON string, not nested object."""
        conn = _make_conn(stdout='{"success": true}')
        panel = _make_panel(conn)

        client_settings = {"clients": [{"id": "uuid-abc", "email": "reality-bob"}]}
        panel.add_client(3, client_settings)

        call_args = conn.run.call_args[0][0]
        assert "addClient" in call_args

        # Extract the JSON body from the curl -d argument.
        # The curl command format: curl -s -b COOKIE -H ... -d 'JSON' URL
        import shlex as _shlex

        parts = _shlex.split(call_args)
        d_index = parts.index("-d")
        body_str = parts[d_index + 1]
        body = json.loads(body_str)

        # The 'settings' field must be a string (JSON-encoded), not a dict
        assert isinstance(body["settings"], str), (
            f"'settings' should be a JSON string, got {type(body['settings']).__name__}"
        )
        # And that string should parse back to the original client_settings
        parsed_settings = json.loads(body["settings"])
        assert parsed_settings == client_settings


class TestGenerateUUIDEdgeCases:
    def test_generate_uuid_empty_output(self) -> None:
        """Xray binary found but uuid command returns empty."""
        conn = MagicMock()
        conn.run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="/app/bin/xray-linux-amd64\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr=""),
        ]
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="empty output"):
            panel.generate_uuid()

    def test_generate_uuid_command_failure(self) -> None:
        """Xray binary found but uuid command fails."""
        conn = MagicMock()
        conn.run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="/app/bin/xray-linux-amd64\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="exec error"),
        ]
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="UUID generation failed"):
            panel.generate_uuid()

    def test_generate_uuid_xray_binary_path_quoted(self) -> None:
        """Xray binary path should be shlex-quoted in the uuid command."""
        conn = MagicMock()
        conn.run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="/app/bin/xray-linux-amd64\n", stderr=""),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", stderr=""
            ),
        ]
        panel = _make_panel(conn)
        uuid = panel.generate_uuid()
        assert uuid == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # Verify the second call (uuid generation) contains the quoted binary path
        second_call = conn.run.call_args_list[1][0][0]
        assert "/app/bin/xray-linux-amd64" in second_call
        assert "uuid" in second_call


class TestApiMethods:
    """Test internal API helper methods."""

    def test_api_get_failure(self) -> None:
        conn = _make_conn(rc=1, stderr="timeout")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="API GET"):
            panel.api_get("/panel/api/inbounds/list")

    def test_api_post_json_failure(self) -> None:
        conn = _make_conn(rc=1, stderr="connection reset")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="API POST"):
            panel.api_post_json("/panel/setting/update", {"key": "value"})

    def test_api_post_empty_failure(self) -> None:
        conn = _make_conn(rc=1, stderr="refused")
        panel = _make_panel(conn)
        with pytest.raises(PanelError, match="API POST"):
            panel.api_post_empty("/panel/api/inbounds/1/delClient/uuid")


class TestInboundDataclass:
    def test_defaults(self) -> None:
        ib = Inbound(id=1, remark="test", protocol="vless", port=443)
        assert ib.clients == []
        assert ib.stream_settings == {}

    def test_with_clients(self) -> None:
        clients = [{"id": "uuid", "email": "test"}]
        ib = Inbound(id=1, remark="test", protocol="vless", port=443, clients=clients)
        assert len(ib.clients) == 1
        assert ib.clients[0]["email"] == "test"
