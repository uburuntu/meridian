"""Smoke tests for CLI commands using CliRunner."""

from __future__ import annotations

from typer.testing import CliRunner

from meridian.cli import app

runner = CliRunner()


class TestCLIBasics:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Meridian" in result.output

    def test_version_command(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "meridian" in result.output

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "setup" in result.output
        assert "client" in result.output
        assert "server" in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app)
        # no_args_is_help=True returns exit code 0 with help text
        assert "setup" in result.output or "Usage" in result.output


class TestSubcommandHelp:
    def test_setup_help(self) -> None:
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "--domain" in result.output
        assert "--sni" in result.output
        assert "--xhttp" in result.output

    def test_client_help(self) -> None:
        result = runner.invoke(app, ["client", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_server_help(self) -> None:
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_check_help(self) -> None:
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "--ai" in result.output

    def test_diagnostics_help(self) -> None:
        result = runner.invoke(app, ["diagnostics", "--help"])
        assert result.exit_code == 0
        assert "--ai" in result.output

    def test_self_update_help(self) -> None:
        result = runner.invoke(app, ["self-update", "--help"])
        assert result.exit_code == 0
