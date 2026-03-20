"""Smoke tests for CLI commands using CliRunner."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from meridian.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestCLIBasics:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "meridian" in _strip_ansi(result.output)

    def test_version_command(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "meridian" in _strip_ansi(result.output)

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "setup" in output
        assert "client" in output
        assert "server" in output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app)
        output = _strip_ansi(result.output)
        assert "setup" in output or "Usage" in output


class TestSubcommandHelp:
    def test_setup_help(self) -> None:
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--domain" in output
        assert "--sni" in output
        assert "--xhttp" in output

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

    def test_check_help(self) -> None:
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "--ai" in _strip_ansi(result.output)

    def test_diagnostics_help(self) -> None:
        result = runner.invoke(app, ["diagnostics", "--help"])
        assert result.exit_code == 0
        assert "--ai" in _strip_ansi(result.output)

    def test_self_update_help(self) -> None:
        result = runner.invoke(app, ["self-update", "--help"])
        assert result.exit_code == 0
