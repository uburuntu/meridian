"""SSH connection helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from meridian.console import fail, info, ok


class ServerConnection:
    """Manage SSH connections to a remote server."""

    def __init__(self, ip: str, user: str = "root", local_mode: bool = False) -> None:
        self.ip = ip
        self.user = user
        self.local_mode = local_mode

    @property
    def _ssh_opts(self) -> list[str]:
        return [
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]

    def run(self, command: str, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess[str]:
        """Run a command on the remote server via SSH."""
        if self.local_mode:
            return subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        cmd = ["ssh", *self._ssh_opts, f"{self.user}@{self.ip}", command]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

    def check_ssh(self) -> None:
        """Verify SSH connectivity. Exits on failure."""
        if self.local_mode:
            return
        info(f"Checking SSH connectivity to {self.user}@{self.ip}")
        try:
            result = self.run("echo ok", timeout=10)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                fail(f"SSH connection failed: {stderr}")
            ok("SSH connection successful")
        except subprocess.TimeoutExpired:
            fail(f"SSH connection timed out (10s) to {self.user}@{self.ip}")
        except FileNotFoundError:
            fail("ssh command not found. Please install OpenSSH client.")

    def detect_local_mode(self) -> bool:
        """Check if we're running on the target server itself."""
        from meridian.config import SERVER_CREDS_DIR

        if (SERVER_CREDS_DIR / "proxy.yml").exists():
            self.local_mode = True
            return True

        # Compare local IP with server IP
        try:
            result = subprocess.run(
                ["curl", "-4", "-s", "--max-time", "3", "https://ifconfig.me"],
                capture_output=True,
                text=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0 and result.stdout.strip() == self.ip:
                self.local_mode = True
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def fetch_credentials(self, local_creds_dir: Path) -> bool:
        """Fetch credentials from server's /etc/meridian/ via SSH."""
        if self.local_mode:
            return False
        try:
            result = subprocess.run(
                [
                    "scp",
                    *self._ssh_opts,
                    f"{self.user}@{self.ip}:/etc/meridian/proxy.yml",
                    str(local_creds_dir / "proxy.yml"),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                (local_creds_dir / "proxy.yml").chmod(0o600)
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False
