"""Tests for SSH connection helpers and tcp_connect."""

from __future__ import annotations

import shlex
import subprocess
from typing import Any
from unittest.mock import patch

import pytest
import typer

from meridian.ssh import ServerConnection, tcp_connect


class TestServerConnectionInit:
    def test_defaults(self) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        assert conn.ip == "1.2.3.4"
        assert conn.user == "root"
        assert conn.local_mode is False
        assert conn.needs_sudo is False

    def test_custom_user(self) -> None:
        conn = ServerConnection(ip="1.2.3.4", user="ubuntu")
        assert conn.user == "ubuntu"

    def test_local_mode(self) -> None:
        conn = ServerConnection(ip="1.2.3.4", local_mode=True)
        assert conn.local_mode is True


class TestServerConnectionRun:
    def test_remote_command_uses_ssh(self) -> None:
        conn = ServerConnection(ip="1.2.3.4", user="root")
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
            conn.run("echo hello")
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "ssh" in cmd
            assert "root@1.2.3.4" in cmd
            assert "echo hello" in cmd

    def test_local_mode_uses_bash(self) -> None:
        conn = ServerConnection(ip="1.2.3.4", local_mode=True)
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
            conn.run("echo hello")
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert cmd == ["bash", "-c", "echo hello"]

    def test_local_mode_needs_sudo(self) -> None:
        conn = ServerConnection(ip="1.2.3.4", local_mode=True)
        conn.needs_sudo = True
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
            conn.run("cat /etc/meridian/proxy.yml")
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert cmd == ["sudo", "-n", "bash", "-c", "cat /etc/meridian/proxy.yml"]

    def test_remote_includes_ssh_opts(self) -> None:
        conn = ServerConnection(ip="5.6.7.8", user="deploy")
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            conn.run("whoami")
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "BatchMode=yes" in cmd
            assert "ConnectTimeout=5" in cmd
            assert "StrictHostKeyChecking=yes" in cmd

    def test_stdin_devnull(self) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            conn.run("echo test")
            kwargs = mock_run.call_args[1]
            assert kwargs["stdin"] == subprocess.DEVNULL


class TestTcpConnect:
    def test_constructs_correct_bash_command(self) -> None:
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            tcp_connect("example.com", 443)
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert cmd[0] == "bash"
            assert cmd[1] == "-c"
            # The command should use /dev/tcp with the host and port
            assert "/dev/tcp/" in cmd[2]
            assert "443" in cmd[2]

    def test_host_is_shell_quoted(self) -> None:
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            tcp_connect("evil;rm -rf /", 443)
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            bash_cmd = cmd[2]
            # The host should be shlex-quoted, making the injection inert
            quoted_host = shlex.quote("evil;rm -rf /")
            assert quoted_host in bash_cmd

    def test_returns_true_on_success(self) -> None:
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            assert tcp_connect("1.2.3.4", 443) is True

    def test_returns_false_on_failure(self) -> None:
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="Connection refused"
            )
            assert tcp_connect("1.2.3.4", 443) is False

    def test_returns_false_on_timeout(self) -> None:
        with patch(
            "meridian.ssh.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="bash", timeout=5),
        ):
            assert tcp_connect("1.2.3.4", 443) is False

    def test_returns_false_on_file_not_found(self) -> None:
        with patch("meridian.ssh.subprocess.run", side_effect=FileNotFoundError):
            assert tcp_connect("1.2.3.4", 443) is False

    def test_custom_timeout(self) -> None:
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            tcp_connect("1.2.3.4", 80, timeout=10)
            kwargs = mock_run.call_args[1]
            assert kwargs["timeout"] == 10

    def test_special_chars_in_host_quoted(self) -> None:
        """Hosts with spaces or quotes should be safely quoted."""
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            tcp_connect("host with spaces", 443)
            bash_cmd = mock_run.call_args[0][0][2]
            quoted = shlex.quote("host with spaces")
            assert quoted in bash_cmd

    def test_stdin_devnull(self) -> None:
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            tcp_connect("1.2.3.4", 443)
            kwargs = mock_run.call_args[1]
            assert kwargs["stdin"] == subprocess.DEVNULL


class TestCheckSSH:
    def test_local_mode_skips_check(self) -> None:
        conn = ServerConnection(ip="1.2.3.4", local_mode=True)
        # Should return without doing anything
        conn.check_ssh()  # no exception

    @patch("meridian.ssh._host_key_known", return_value=True)
    def test_ssh_success(self, _mock_hk: Any) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch.object(conn, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
            conn.check_ssh()  # should not raise

    @patch("meridian.ssh._host_key_known", return_value=True)
    def test_ssh_failure_exits(self, _mock_hk: Any) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch.object(conn, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=255, stdout="", stderr="Permission denied"
            )
            with pytest.raises(typer.Exit):
                conn.check_ssh()

    @patch("meridian.ssh._host_key_known", return_value=True)
    def test_ssh_timeout_exits(self, _mock_hk: Any) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch.object(conn, "run", side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=10)):
            with pytest.raises(typer.Exit):
                conn.check_ssh()

    @patch("meridian.ssh._host_key_known", return_value=True)
    def test_ssh_not_found_exits(self, _mock_hk: Any) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch.object(conn, "run", side_effect=FileNotFoundError):
            with pytest.raises(typer.Exit):
                conn.check_ssh()

    @patch("meridian.ssh._verify_host_key", return_value=False)
    @patch("meridian.ssh._host_key_known", return_value=False)
    def test_unknown_host_key_rejected_exits(self, _mock_hk: Any, _mock_vhk: Any) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with pytest.raises(typer.Exit):
            conn.check_ssh()

    @patch("meridian.ssh._verify_host_key", return_value=True)
    @patch("meridian.ssh._host_key_known", return_value=False)
    def test_unknown_host_key_accepted_continues(self, _mock_hk: Any, _mock_vhk: Any) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch.object(conn, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")
            conn.check_ssh()  # should not raise
