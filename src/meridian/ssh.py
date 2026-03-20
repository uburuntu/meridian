"""SSH connection helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from meridian.console import err_console, fail, info, ok


class ServerConnection:
    """Manage SSH connections to a remote server.

    Non-root remote users: Ansible handles privilege escalation via ansible_become.
    Non-root local users: CLI detects and suggests `sudo meridian`.
    Passwordless sudo is required (standard on AWS/GCP/Azure/DO).
    """

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
                stdin=subprocess.DEVNULL,
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
                err_console.print(f"\n  [error]SSH connection failed:[/error] {stderr}")
                err_console.print(f"  [dim]1. Copy your SSH key:  ssh-copy-id {self.user}@{self.ip}[/dim]")
                err_console.print(f"  [dim]2. Test manually:      ssh {self.user}@{self.ip}[/dim]")
                err_console.print("  [dim]3. Different user:     meridian setup IP --user ubuntu[/dim]")
                fail(f"SSH connection failed to {self.user}@{self.ip}")
            ok("SSH connection successful")
        except subprocess.TimeoutExpired:
            fail(f"SSH connection timed out (10s) to {self.user}@{self.ip}")
        except FileNotFoundError:
            fail("ssh command not found. Please install OpenSSH client.")

    def detect_local_mode(self) -> bool:
        """Check if we're running on the target server itself.

        Local mode requires root access to /etc/meridian/. If we detect we're
        on the server but not root, we suggest `sudo meridian` instead.
        """
        from meridian.config import SERVER_CREDS_DIR

        # Check if /etc/meridian/proxy.yml is readable (root only)
        proxy = SERVER_CREDS_DIR / "proxy.yml"
        try:
            if proxy.is_file() and proxy.stat().st_size > 0:
                self.local_mode = True
                return True
        except (PermissionError, OSError):
            # We can see the directory exists but can't read — non-root on server
            if _is_on_server(self.ip):
                self_bin = shutil.which("meridian") or "~/.local/bin/meridian"
                err_console.print(
                    "\n  [warn]![/warn] Running on the server as non-root. Meridian needs root to access credentials."
                )
                err_console.print(f"  [dim]Run with sudo:  sudo -E {self_bin} setup {self.ip}[/dim]")
                err_console.print(f"  [dim]Or from laptop:  meridian setup {self.ip} --user {self.user}[/dim]\n")
                fail("Root access required on the server itself")
            return False

        # Check if our public IP matches the target (root without prior deploy)
        if _is_on_server(self.ip):
            self.local_mode = True
            return True

        return False

    def fetch_credentials(self, local_creds_dir: Path) -> bool:
        """Fetch credentials from server's /etc/meridian/ via SCP.

        In local mode (root), copies directly from /etc/meridian/.
        In remote mode, uses SCP.
        """
        if self.local_mode:
            return self._copy_local_credentials(local_creds_dir)

        local_creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
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
                # Also fetch clients tracking file (best-effort)
                subprocess.run(
                    [
                        "scp",
                        *self._ssh_opts,
                        f"{self.user}@{self.ip}:/etc/meridian/proxy-clients.yml",
                        str(local_creds_dir / "proxy-clients.yml"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    stdin=subprocess.DEVNULL,
                )
                clients_file = local_creds_dir / "proxy-clients.yml"
                if clients_file.exists():
                    clients_file.chmod(0o600)
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def _copy_local_credentials(self, local_creds_dir: Path) -> bool:
        """Copy credentials from /etc/meridian/ in local mode (root)."""
        from meridian.config import SERVER_CREDS_DIR

        src = SERVER_CREDS_DIR / "proxy.yml"
        dst = local_creds_dir / "proxy.yml"

        if dst == src:
            return True

        try:
            if src.is_file():
                local_creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(str(src), str(dst))
                dst.chmod(0o600)
                clients_src = SERVER_CREDS_DIR / "proxy-clients.yml"
                if clients_src.is_file():
                    shutil.copy2(str(clients_src), str(local_creds_dir / "proxy-clients.yml"))
                    (local_creds_dir / "proxy-clients.yml").chmod(0o600)
                return True
        except (PermissionError, OSError):
            pass
        return False


def _is_on_server(ip: str) -> bool:
    """Check if our public IP matches the target server's IP."""
    try:
        result = subprocess.run(
            ["curl", "-4", "-s", "--max-time", "3", "https://ifconfig.me"],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode == 0 and result.stdout.strip() == ip
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
