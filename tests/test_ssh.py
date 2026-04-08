"""Tests for SSH connection helpers and tcp_connect."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest
import typer

from meridian.ssh import ServerConnection, _verify_host_key, tcp_connect


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
            assert "ConnectTimeout=10" in cmd
            assert "StrictHostKeyChecking=yes" in cmd

    def test_stdin_devnull(self) -> None:
        conn = ServerConnection(ip="1.2.3.4")
        with patch("meridian.ssh.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            conn.run("echo test")
            kwargs = mock_run.call_args[1]
            assert kwargs["stdin"] == subprocess.DEVNULL


class TestTcpConnect:
    def test_returns_true_on_success(self) -> None:
        mock_sock = MagicMock()
        with patch("socket.socket", return_value=mock_sock):
            assert tcp_connect("1.2.3.4", 443) is True
            mock_sock.settimeout.assert_called_once_with(5)
            mock_sock.connect.assert_called_once_with(("1.2.3.4", 443))
            mock_sock.close.assert_called_once()

    def test_returns_false_on_connection_refused(self) -> None:
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError
        with patch("socket.socket", return_value=mock_sock):
            assert tcp_connect("1.2.3.4", 443) is False

    def test_returns_false_on_timeout(self) -> None:
        import socket

        mock_sock = MagicMock()
        mock_sock.connect.side_effect = socket.timeout
        with patch("socket.socket", return_value=mock_sock):
            assert tcp_connect("1.2.3.4", 443) is False

    def test_returns_false_on_os_error(self) -> None:
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = OSError("Network unreachable")
        with patch("socket.socket", return_value=mock_sock):
            assert tcp_connect("1.2.3.4", 443) is False

    def test_custom_timeout(self) -> None:
        mock_sock = MagicMock()
        with patch("socket.socket", return_value=mock_sock):
            tcp_connect("1.2.3.4", 80, timeout=10)
            mock_sock.settimeout.assert_called_once_with(10)


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


class TestVerifyHostKey:
    """Tests for _verify_host_key — host key scanning, verification, and storage."""

    SCAN_OUTPUT = (
        "1.2.3.4 ssh-rsa AAAAB3NzaC1yc2EAAA...\n"
        "1.2.3.4 ecdsa-sha2-nistp256 AAAAE2VjZHNh...\n"
        "1.2.3.4 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...\n"
    )

    def test_writes_only_preferred_key_not_all(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only the verified (preferred) key should be written to known_hosts."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(mode=0o700)
        known_hosts = ssh_dir / "known_hosts"
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        scan_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=self.SCAN_OUTPUT, stderr="")
        fingerprint_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="256 SHA256:abc... 1.2.3.4 (ED25519)\n", stderr=""
        )

        def mock_subprocess_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "ssh-keyscan":
                return scan_result
            if cmd[0] == "ssh-keygen":
                return fingerprint_result
            raise ValueError(f"Unexpected command: {cmd}")

        with (
            patch("meridian.ssh.subprocess.run", side_effect=mock_subprocess_run),
            patch("builtins.open", mock_open()) as tty_mock,
        ):
            # Simulate user typing "y" at the TTY prompt
            tty_handle = MagicMock()
            tty_handle.readline.return_value = "y\n"
            tty_mock.return_value.__enter__ = lambda s: tty_handle

            # But we need the real file write for known_hosts — use a different approach
            pass

        # Use a simpler approach: patch /dev/tty read, let file writes go through
        with patch("meridian.ssh.subprocess.run", side_effect=mock_subprocess_run):
            # Patch the TTY open to return "y"
            original_open = open

            def patched_open(path: Any, *args: Any, **kwargs: Any) -> Any:
                if str(path) == "/dev/tty":
                    m = MagicMock()
                    m.readline.return_value = "y\n"
                    m.__enter__ = lambda s: m
                    m.__exit__ = lambda s, *a: None
                    return m
                return original_open(path, *args, **kwargs)

            with patch("builtins.open", side_effect=patched_open):
                result = _verify_host_key("1.2.3.4")

        assert result is True
        assert known_hosts.exists()
        lines = known_hosts.read_text().strip().splitlines()
        # Only 1 key written (the preferred ed25519), not all 3
        assert len(lines) == 1
        assert "ssh-ed25519" in lines[0]

    def test_prefers_ed25519_over_rsa(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """ed25519 should be preferred over ecdsa and rsa."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(mode=0o700)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        scan_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=self.SCAN_OUTPUT, stderr="")
        fp_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="256 SHA256:xyz... (ED25519)\n", stderr=""
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "ssh-keyscan":
                return scan_result
            return fp_result

        original_open = open

        def patched_open(path: Any, *args: Any, **kwargs: Any) -> Any:
            if str(path) == "/dev/tty":
                m = MagicMock()
                m.readline.return_value = "y\n"
                m.__enter__ = lambda s: m
                m.__exit__ = lambda s, *a: None
                return m
            return original_open(path, *args, **kwargs)

        with (
            patch("meridian.ssh.subprocess.run", side_effect=mock_run),
            patch("builtins.open", side_effect=patched_open),
        ):
            _verify_host_key("1.2.3.4")

        known_hosts = ssh_dir / "known_hosts"
        content = known_hosts.read_text()
        assert "ssh-ed25519" in content
        assert "ssh-rsa" not in content
        assert "ecdsa" not in content

    def test_no_tty_fails_instead_of_auto_accept(self) -> None:
        """Non-interactive mode should refuse host key, not silently accept."""
        scan_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1.2.3.4 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...\n", stderr=""
        )
        fp_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="256 SHA256:abc... (ED25519)\n", stderr=""
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "ssh-keyscan":
                return scan_result
            return fp_result

        original_open = open

        def patched_open(path: Any, *args: Any, **kwargs: Any) -> Any:
            if str(path) == "/dev/tty":
                raise OSError("No TTY")
            return original_open(path, *args, **kwargs)

        with (
            patch("meridian.ssh.subprocess.run", side_effect=mock_run),
            patch("builtins.open", side_effect=patched_open),
        ):
            with pytest.raises(typer.Exit) as exc_info:
                _verify_host_key("1.2.3.4")
            assert exc_info.value.exit_code == 1

    def test_user_rejects_key_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """User answering 'n' should return False without writing anything."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(mode=0o700)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        scan_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1.2.3.4 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...\n", stderr=""
        )
        fp_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="256 SHA256:abc... (ED25519)\n", stderr=""
        )

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "ssh-keyscan":
                return scan_result
            return fp_result

        original_open = open

        def patched_open(path: Any, *args: Any, **kwargs: Any) -> Any:
            if str(path) == "/dev/tty":
                m = MagicMock()
                m.readline.return_value = "n\n"
                m.__enter__ = lambda s: m
                m.__exit__ = lambda s, *a: None
                return m
            return original_open(path, *args, **kwargs)

        with (
            patch("meridian.ssh.subprocess.run", side_effect=mock_run),
            patch("builtins.open", side_effect=patched_open),
        ):
            result = _verify_host_key("1.2.3.4")

        assert result is False
        known_hosts = ssh_dir / "known_hosts"
        assert not known_hosts.exists()
