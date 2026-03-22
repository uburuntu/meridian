"""SSH connection helpers."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from meridian.console import err_console, fail, info, ok, warn


def _shell_quote(s: str) -> str:
    """Quote a string for safe embedding inside bash -c '...'."""
    return shlex.quote(s)


SSH_OPTS: list[str] = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=5",
    "-o",
    "StrictHostKeyChecking=yes",
]


def _host_key_known(ip: str) -> bool:
    """Check if the host key for this IP is already in known_hosts."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-F", ip],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _verify_host_key(ip: str) -> bool:
    """Scan, display, and prompt user to verify the SSH host key.

    Returns True if the user accepts (key added to known_hosts), False otherwise.
    Uses ssh-keyscan to fetch the key and ssh-keygen to compute the fingerprint.
    """
    # Scan the host key
    try:
        result = subprocess.run(
            ["ssh-keyscan", "-T", "5", ip],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0 or not result.stdout.strip():
            warn(f"Could not scan host key for {ip}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        warn(f"Could not scan host key for {ip}")
        return False

    key_lines = [line for line in result.stdout.strip().splitlines() if line and not line.startswith("#")]
    if not key_lines:
        warn(f"No host keys found for {ip}")
        return False

    # Prefer ed25519 > ecdsa > rsa
    preferred = None
    for pref in ("ssh-ed25519", "ecdsa-sha2", "ssh-rsa"):
        for line in key_lines:
            if pref in line:
                preferred = line
                break
        if preferred:
            break
    if not preferred:
        preferred = key_lines[0]

    # Compute fingerprint
    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", "-"],
            input=preferred,
            capture_output=True,
            text=True,
            timeout=5,
        )
        fingerprint = result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        fingerprint = ""

    # Display to user
    key_type = preferred.split()[1] if len(preferred.split()) >= 2 else "unknown"
    # key_type is the full key data, extract algorithm from the 3rd field
    parts = preferred.split()
    algo = parts[1] if len(parts) >= 3 else key_type

    err_console.print()
    err_console.print(f"  [warn]![/warn] First connection to {ip}")
    if fingerprint:
        err_console.print("  [dim]Host key fingerprint:[/dim]")
        err_console.print(f"  [bold]{fingerprint}[/bold]")
    else:
        err_console.print(f"  [dim]Host key type: {algo}[/dim]")
    err_console.print()
    err_console.print("  [dim]Verify this matches your VPS provider's console.[/dim]")
    err_console.print("  [dim]A mismatch may indicate a network attack.[/dim]")

    # Prompt user
    try:
        with open("/dev/tty") as tty:
            err_console.print("\n  [info]\u2192[/info] Trust this host key? [dim][Y/n][/dim] ", end="")
            answer = tty.readline().strip().lower()
    except OSError:
        # No TTY — fall back to accept-new behavior for non-interactive use
        warn("No terminal available — accepting host key automatically")
        answer = "y"

    if answer not in ("", "y", "yes"):
        return False

    # Add all scanned keys to known_hosts
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(mode=0o700, exist_ok=True)
    with open(known_hosts, "a") as f:
        for line in key_lines:
            f.write(line + "\n")

    ok("Host key saved")
    return True


class ServerConnection:
    """Manage SSH connections to a remote server.

    Non-root remote users: commands are wrapped in sudo -n sh -c via SSH.
    Non-root local users: detect_local_mode sets needs_sudo, commands run
    via sudo -n bash -c for privilege escalation.
    Passwordless sudo is required (standard on AWS/GCP/Azure/DO).
    """

    def __init__(self, ip: str, user: str = "root", local_mode: bool = False) -> None:
        self.ip = ip
        self.user = user
        self.local_mode = local_mode
        self.needs_sudo = False  # on-server non-root — run commands via sudo

    @property
    def _ssh_opts(self) -> list[str]:
        return SSH_OPTS

    def run(
        self, command: str, timeout: int = 30, check: bool = False, *, sudo: bool | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a command on the remote server via SSH.

        Args:
            command: Shell command to execute.
            timeout: Timeout in seconds.
            check: Not used (kept for API compatibility).
            sudo: Force sudo wrapping. None = auto (sudo when user != root).
        """
        use_sudo = sudo if sudo is not None else (self.user != "root")

        if self.local_mode:
            if self.needs_sudo or use_sudo:
                cmd = ["sudo", "-n", "bash", "-c", command]
            else:
                cmd = ["bash", "-c", command]
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        # Remote SSH
        if use_sudo and not self.needs_sudo:
            # Non-root remote user: wrap in sudo via SSH
            # SSH passes the command string to the remote shell, which handles
            # the first layer of quoting. sudo -n sh -c adds a second layer.
            command = f"sudo -n sh -c {_shell_quote(command)}"
        cmd = ["ssh", *self._ssh_opts, f"{self.user}@{self.ip}", command]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

    def check_ssh(self) -> None:
        """Verify SSH connectivity. Exits on failure.

        On first connection to an unknown host, scans the host key,
        displays the fingerprint, and prompts the user to verify it.
        """
        if self.local_mode:
            return
        info(f"Checking SSH connectivity to {self.user}@{self.ip}")

        # Verify host key on first connection
        if not _host_key_known(self.ip):
            if not _verify_host_key(self.ip):
                fail(
                    f"Host key for {self.ip} not accepted",
                    hint="Verify the fingerprint matches your VPS provider's console.",
                    hint_type="user",
                )

        try:
            result = self.run("echo ok", timeout=10)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                # Host key changed — warn clearly
                if "REMOTE HOST IDENTIFICATION HAS CHANGED" in stderr:
                    err_console.print(f"\n  [error]Host key for {self.ip} has CHANGED![/error]")
                    err_console.print("  [warn]This could indicate a network attack (MitM).[/warn]")
                    err_console.print("  [dim]If you recently rebuilt this server, remove the old key:[/dim]")
                    err_console.print(f"  [dim]  ssh-keygen -R {self.ip}[/dim]")
                    fail(f"Host key verification failed for {self.ip}", hint_type="system")
                err_console.print(f"\n  [error]SSH connection failed:[/error] {stderr}")
                err_console.print(f"  [dim]1. Copy your SSH key:  ssh-copy-id {self.user}@{self.ip}[/dim]")
                err_console.print(f"  [dim]2. Test manually:      ssh {self.user}@{self.ip}[/dim]")
                err_console.print("  [dim]3. Different user:     meridian deploy IP --user ubuntu[/dim]")
                fail(f"SSH connection failed to {self.user}@{self.ip}", hint_type="system")
            ok("SSH connection successful")
        except subprocess.TimeoutExpired:
            fail(f"SSH connection timed out (10s) to {self.user}@{self.ip}", hint_type="system")
        except FileNotFoundError:
            fail("ssh command not found. Please install OpenSSH client.", hint_type="system")

    def detect_local_mode(self) -> bool:
        """Check if we're running on the target server itself.

        Local mode requires root access to /etc/meridian/. If we detect we're
        on the server but not root, we set needs_sudo=True and run commands
        via sudo -n bash -c for privilege escalation.
        """
        from meridian.config import SERVER_CREDS_DIR

        # Check if /etc/meridian/proxy.yml is readable (root only)
        proxy = SERVER_CREDS_DIR / "proxy.yml"
        try:
            if proxy.is_file() and proxy.stat().st_size > 0:
                self.local_mode = True
                return True
        except (PermissionError, OSError):
            # Non-root on server — use local mode with sudo for commands
            if _is_on_server(self.ip):
                warn("Running as non-root on the server. Using sudo for commands.")
                self.local_mode = True
                self.needs_sudo = True
                return True
            return False

        # Check if our public IP matches the target (root without prior deploy)
        if _is_on_server(self.ip):
            self.local_mode = True
            if self.user != "root":
                self.needs_sudo = True
                warn("Running as non-root on the server. Using sudo for commands.")
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
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def _copy_local_credentials(self, local_creds_dir: Path) -> bool:
        """Copy credentials from /etc/meridian/ in local mode.

        When needs_sudo is set, uses sudo to read root-owned credential files.
        """
        from meridian.config import SERVER_CREDS_DIR

        src = SERVER_CREDS_DIR / "proxy.yml"
        dst = local_creds_dir / "proxy.yml"

        if dst == src:
            return True

        local_creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Copy main credentials (required)
        if not self._copy_one_file(SERVER_CREDS_DIR / "proxy.yml", local_creds_dir / "proxy.yml"):
            return False
        return True

    def _copy_one_file(self, src: Path, dst: Path) -> bool:
        """Copy a single file, using sudo if needed. Returns True on success."""
        if self.needs_sudo:
            try:
                result = subprocess.run(
                    ["sudo", "-n", "cat", str(src)],
                    capture_output=True,
                    timeout=5,
                    stdin=subprocess.DEVNULL,
                )
                if result.returncode != 0:
                    return False
                dst.write_bytes(result.stdout)
                dst.chmod(0o600)
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
        try:
            if src.is_file():
                shutil.copy2(str(src), str(dst))
                dst.chmod(0o600)
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


def tcp_connect(host: str, port: int, timeout: int = 5) -> bool:
    """Test TCP connectivity to host:port using bash /dev/tcp."""
    import shlex

    try:
        q_host = shlex.quote(host)
        result = subprocess.run(
            ["bash", "-c", f"echo >/dev/tcp/{q_host}/{port}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
