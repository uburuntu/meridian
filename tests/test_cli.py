"""Smoke tests for CLI commands using CliRunner."""

from __future__ import annotations

import json
import re

from typer.testing import CliRunner

import meridian.cli as cli
from meridian.cli import app
from meridian.console import is_json_mode, set_json_mode, set_quiet_mode

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _reset_output_modes() -> None:
    set_json_mode(False)
    set_quiet_mode(False)


def _assert_machine_json_without_banner(output: str) -> dict[str, object]:
    assert "Meridian v" not in output
    return json.loads(output)


class TestCLIBasics:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "meridian" in _strip_ansi(result.output)

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "deploy" in output
        assert "client" in output
        assert "server" in output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app)
        output = _strip_ansi(result.output)
        assert "deploy" in output or "Usage" in output


class TestSubcommandHelp:
    def test_deploy_help(self) -> None:
        result = runner.invoke(app, ["deploy", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--domain" in output
        assert "--sni" in output

    def test_client_help(self) -> None:
        result = runner.invoke(app, ["client", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "add" in output
        assert "list" in output
        assert "remove" in output

    def test_server_help(self) -> None:
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "add" in output
        assert "list" in output
        assert "remove" in output

    def test_fleet_help(self) -> None:
        result = runner.invoke(app, ["fleet", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "status" in output
        assert "inventory" in output
        assert "recover" in output

    def test_api_help(self) -> None:
        result = runner.invoke(app, ["api", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "commands" in output
        assert "schemas" in output
        assert "schema" in output

    def test_fleet_status_help_documents_command_json(self) -> None:
        result = runner.invoke(app, ["fleet", "status", "--help"])
        assert result.exit_code == 0
        assert "--json" in _strip_ansi(result.output)

    def test_fleet_inventory_accepts_command_json(self, monkeypatch) -> None:
        called: dict[str, bool] = {}

        def fake_run_inventory() -> None:
            called["json"] = is_json_mode()

        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr("meridian.commands.fleet.run_inventory", fake_run_inventory)

        result = runner.invoke(app, ["fleet", "inventory", "--json"])

        set_json_mode(False)
        set_quiet_mode(False)
        assert result.exit_code == 0
        assert called["json"] is True

    def test_client_list_accepts_command_json(self, monkeypatch) -> None:
        called: dict[str, bool] = {}

        def fake_run_list(*_args: object, **_kwargs: object) -> None:
            called["json"] = is_json_mode()

        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr("meridian.commands.client.run_list", fake_run_list)

        result = runner.invoke(app, ["client", "list", "--json"])

        set_json_mode(False)
        set_quiet_mode(False)
        assert result.exit_code == 0
        assert called["json"] is True

    def test_client_show_accepts_command_json(self, monkeypatch) -> None:
        called: dict[str, bool] = {}

        def fake_run_show(*_args: object, **_kwargs: object) -> None:
            called["json"] = is_json_mode()

        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr("meridian.commands.client.run_show", fake_run_show)

        result = runner.invoke(app, ["client", "show", "alice", "--json"])

        set_json_mode(False)
        set_quiet_mode(False)
        assert result.exit_code == 0
        assert called["json"] is True

    def test_preflight_help(self) -> None:
        result = runner.invoke(app, ["preflight", "--help"])
        assert result.exit_code == 0
        assert "--ai" in _strip_ansi(result.output)

    def test_doctor_help(self) -> None:
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "--ai" in _strip_ansi(result.output)

    def test_rage_alias(self) -> None:
        result = runner.invoke(app, ["rage", "--help"])
        assert result.exit_code == 0
        assert "--ai" in _strip_ansi(result.output)

    def test_update_help(self) -> None:
        result = runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0


class TestApiContractCLI:
    def test_api_schemas_json_is_parseable_machine_output(self, monkeypatch) -> None:
        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)

        result = runner.invoke(app, ["api", "schemas", "--json"])

        _reset_output_modes()
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["command"] == "api.schemas"
        assert payload["data"]["schemas"]
        assert "Meridian v" not in result.output

    def test_api_commands_json_lists_command_contracts(self, monkeypatch) -> None:
        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)

        result = runner.invoke(app, ["api", "commands", "--json"])

        _reset_output_modes()
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["command"] == "api.commands"
        commands = {item["command"]: item for item in payload["data"]["commands"]}
        assert commands["plan"]["envelope_schema"] == "plan-envelope"
        assert commands["fleet.status"]["data_schema"] == "fleet-status"
        assert commands["client.list"]["argv"] == ["client", "list"]

    def test_api_schema_envelope_error_is_command_scoped_json(self, monkeypatch) -> None:
        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)

        result = runner.invoke(app, ["api", "schema", "missing", "--envelope"])

        _reset_output_modes()
        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["command"] == "api.schema"
        assert payload["status"] == "failed"
        assert payload["errors"][0]["category"] == "user"

    def test_api_schema_raw_schema_preserves_sensitive_property_names(self, monkeypatch) -> None:
        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)

        result = runner.invoke(app, ["api", "schema", "client-show"])

        _reset_output_modes()
        assert result.exit_code == 0
        payload = json.loads(result.output)
        client_props = payload["$defs"]["ClientDetail"]["properties"]
        handoff_props = payload["$defs"]["ClientHandoff"]["properties"]
        assert "subscription_url" not in client_props
        assert "share_url" not in client_props
        assert handoff_props["subscription_available"]["type"] == "boolean"
        assert handoff_props["share_available"]["type"] == "boolean"

    def test_api_schema_raw_error_is_machine_readable(self, monkeypatch) -> None:
        set_json_mode(False)
        set_quiet_mode(False)
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)

        result = runner.invoke(app, ["api", "schema", "missing"])

        _reset_output_modes()
        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["command"] == "api.schema"
        assert payload["status"] == "failed"
        assert payload["errors"][0]["category"] == "user"


class TestCommandLocalJsonQuieting:
    def test_plan_command_json_suppresses_banner(self, monkeypatch) -> None:
        def fake_run(*, json_output: bool) -> None:
            assert json_output is True
            print('{"ok": true}')

        _reset_output_modes()
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr(cli.sys, "argv", ["meridian", "plan", "--json"])
        monkeypatch.setattr("meridian.commands.plan.run", fake_run)

        result = runner.invoke(app, ["plan", "--json"])

        _reset_output_modes()
        assert result.exit_code == 0
        assert _assert_machine_json_without_banner(result.output) == {"ok": True}

    def test_client_list_command_json_suppresses_banner(self, monkeypatch) -> None:
        def fake_run_list(*_args: object, **_kwargs: object) -> None:
            print('{"ok": true}')

        _reset_output_modes()
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr(cli.sys, "argv", ["meridian", "client", "list", "--json"])
        monkeypatch.setattr("meridian.commands.client.run_list", fake_run_list)

        result = runner.invoke(app, ["client", "list", "--json"])

        _reset_output_modes()
        assert result.exit_code == 0
        assert _assert_machine_json_without_banner(result.output) == {"ok": True}

    def test_client_show_command_json_suppresses_banner(self, monkeypatch) -> None:
        def fake_run_show(*_args: object, **_kwargs: object) -> None:
            print('{"ok": true}')

        _reset_output_modes()
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr(cli.sys, "argv", ["meridian", "client", "show", "alice", "--json"])
        monkeypatch.setattr("meridian.commands.client.run_show", fake_run_show)

        result = runner.invoke(app, ["client", "show", "alice", "--json"])

        _reset_output_modes()
        assert result.exit_code == 0
        assert _assert_machine_json_without_banner(result.output) == {"ok": True}

    def test_fleet_status_command_json_suppresses_banner(self, monkeypatch) -> None:
        def fake_run_status() -> None:
            print('{"ok": true}')

        _reset_output_modes()
        monkeypatch.setattr(cli, "DISABLE_UPDATE_CHECK", True)
        monkeypatch.setattr(cli.sys, "argv", ["meridian", "fleet", "status", "--json"])
        monkeypatch.setattr("meridian.commands.fleet.run_status", fake_run_status)

        result = runner.invoke(app, ["fleet", "status", "--json"])

        _reset_output_modes()
        assert result.exit_code == 0
        assert _assert_machine_json_without_banner(result.output) == {"ok": True}
