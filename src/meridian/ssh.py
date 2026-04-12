"""SSH connection helpers."""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
from pathlib import Path

from meridian.console import err_console, info, ok, warn

logger = logging.getLogger("meridian.ssh")


class SSHError(Exception):
    """Raised when an SSH operation fails.

    Attributes:
        hint: Optional recovery suggestion for the user.
        hint_type: Error category — "user", "system", or "bug".
    """

    def __init__(self, msg: str, *, hint: str = "", hint_type: str = "system") -> None:
        super().__init__(msg)
        self.hint = hint
        self.hint_type = hint_type


SSH_OPTS: list[str] = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=yes",
]


def scp_host(ip: str) -> str:
    """Format IP for SCP host:path syntax (brackets IPv6)."""
    if ":" in ip and not ip.startswith("["):
        return f"[{ip}]"
    return ip


def _host_key_known(ip: str, port: int = 22) -> bool:
    """Check if the host key for this IP is already in known_hosts."""
    # ssh-keygen -F uses [host]:port notation for non-default ports
    lookup = f"[{ip}]:{port}" if port != 22 else ip
    try:
        result = subprocess.run(
            ["ssh-keygen", "-F", lookup],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _verify_host_key(ip: str, port: int = 22) -> bool:
    """Scan, display, and prompt user to verify the SSH host key.

    Returns True if the user accepts (key added to known_hosts), False otherwise.
    Uses ssh-keyscan to fetch the key and ssh-keygen to compute the fingerprint.
    """
    # Scan the host key
    keyscan_cmd = ["ssh-keyscan", "-T", "5"]
    if port != 22:
        keyscan_cmd.extend(["-p", str(port)])
    keyscan_cmd.append(ip)
    try:
        result = subprocess.run(
            keyscan_cmd,
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
        # No TTY — refuse to accept host key silently (MitM risk)
        raise SSHError(
            f"Cannot verify host key for {ip} (no terminal available)",
            hint="Run interactively, or pre-add the key: ssh-keyscan IP >> ~/.ssh/known_hosts",
            hint_type="user",
        )

    if answer not in ("", "y", "yes"):
        return False

    # Add only the verified key to known_hosts (user only saw this fingerprint)
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(mode=0o700, exist_ok=True)
    with open(known_hosts, "a") as f:
        f.write(preferred + "\n")

    ok("Host key saved")
    return True


class ServerConnection:
    """Manage SSH connections to a remote server.

    Non-root remote users: commands are wrapped in sudo -n sh -c via SSH.
    Non-root local users: detect_local_mode sets needs_sudo, commands run
    via sudo -n bash -c for privilege escalation.
    Passwordless sudo is required (standard on AWS/GCP/Azure/DO).
    """

    def __init__(self, ip: str, user: str = "root", local_mode: bool = False, port: int = 22) -> None:
        self.ip = ip
        self.user = user
        self.port = port
        self.local_mode = local_mode
        self.needs_sudo = False  # on-server non-root — run commands via sudo

    @property
    def _ssh_opts(self) -> list[str]:
        opts = list(SSH_OPTS)
        if self.port != 22:
            opts.extend(["-p", str(self.port)])
        return opts

    @property
    def _scp_opts(self) -> list[str]:
        """SSH options for SCP commands (uses -P for port, not -p)."""
        opts = list(SSH_OPTS)
        if self.port != 22:
            opts.extend(["-P", str(self.port)])
        return opts

    @property
    def _scp_host(self) -> str:
        """Host string for SCP commands (brackets IPv6 addresses)."""
        if ":" in self.ip and not self.ip.startswith("["):
            return f"[{self.ip}]"
        return self.ip

    def run(self, command: str, timeout: int = 30, *, sudo: bool | None = None) -> subprocess.CompletedProcess[str]:
        """Run a command on the remote server via SSH.

        Args:
            command: Shell command to execute.
            timeout: Timeout in seconds.
            sudo: Force sudo wrapping. None = auto (sudo when user != root).

        Returns a synthetic CompletedProcess with returncode=124 if the
        command times out (matching GNU ``timeout`` convention), instead
        of letting ``subprocess.TimeoutExpired`` crash the caller.
        """
        use_sudo = sudo if sudo is not None else (self.user != "root")
        logger.debug("SSH %s@%s: %s", self.user, self.ip, command[:200])

        if self.local_mode:
            if self.needs_sudo or use_sudo:
                cmd = ["sudo", "-n", "bash", "-c", command]
            else:
                cmd = ["bash", "-c", command]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    stdin=subprocess.DEVNULL,
                )
                logger.debug("SSH rc=%d", result.returncode)
                return result
            except subprocess.TimeoutExpired:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=124,
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                )
        # Remote SSH
        if use_sudo and not self.needs_sudo:
            # Non-root remote user: wrap in sudo via SSH
            # SSH passes the command string to the remote shell, which handles
            # the first layer of quoting. sudo -n sh -c adds a second layer.
            command = f"sudo -n sh -c {shlex.quote(command)}"
        cmd = ["ssh", *self._ssh_opts, f"{self.user}@{self.ip}", command]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
            logger.debug("SSH rc=%d", result.returncode)
            return result
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
            )

    def check_ssh(self) -> None:
        """Verify SSH connectivity. Exits on failure.

        On first connection to an unknown host, scans the host key,
        displays the fingerprint, and prompts the user to verify it.
        """
        if self.local_mode:
            return
        info(f"Checking SSH connectivity to {self.user}@{self.ip}" + (f":{self.port}" if self.port != 22 else ""))

        # Verify host key on first connection
        if not _host_key_known(self.ip, self.port):
            if not _verify_host_key(self.ip, self.port):
                raise SSHError(
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
                    raise SSHError(f"Host key verification failed for {self.ip}", hint_type="system")
                # sudo not found — non-root user on a system without sudo
                if self.user != "root" and ("sudo" in stderr and ("not found" in stderr or "No such file" in stderr)):
                    raise SSHError(
                        f"sudo is not installed on {self.ip}",
                        hint=f"Install it as root: ssh root@{self.ip} 'apt-get install -y sudo'",
                        hint_type="system",
                    )
                err_console.print(f"\n  [error]SSH connection failed:[/error] {stderr}")
                err_console.print(f"  [dim]1. Copy your SSH key:  ssh-copy-id {self.user}@{self.ip}[/dim]")
                err_console.print(f"  [dim]2. Test manually:      ssh {self.user}@{self.ip}[/dim]")
                err_console.print("  [dim]3. Different user:     meridian deploy IP --user ubuntu[/dim]")
                raise SSHError(f"SSH connection failed to {self.user}@{self.ip}", hint_type="system")
            ok("SSH connection successful")
        except subprocess.TimeoutExpired:
            raise SSHError(f"SSH connection timed out (10s) to {self.user}@{self.ip}", hint_type="system")
        except FileNotFoundError:
            raise SSHError("ssh command not found. Please install OpenSSH client.", hint_type="system")

    def detect_local_mode(self) -> bool:
        """Check if we're running on the target server itself.

        Detection is file-based only: /etc/meridian/node.yml (v4) or
        /etc/meridian/proxy.yml (v3 compat) readable (root), or
        /etc/meridian/ directory exists but files not readable (non-root).

        Does NOT use public IP matching — that produces false positives when
        the user is connected to the server via TUN mode (VPN), since their
        outbound IP matches the server IP.
        """
        from meridian.config import SERVER_CREDS_DIR, SERVER_NODE_CONFIG

        file_check_failed = False

        # v4: node.yml
        try:
            if SERVER_NODE_CONFIG.is_file() and SERVER_NODE_CONFIG.stat().st_size > 0:
                self.local_mode = True
                return True
        except (PermissionError, OSError):
            file_check_failed = True

        # v3 compat: proxy.yml
        proxy = SERVER_CREDS_DIR / "proxy.yml"
        try:
            if proxy.is_file() and proxy.stat().st_size > 0:
                self.local_mode = True
                return True
        except (PermissionError, OSError):
            file_check_failed = True

        # Dir exists but files not readable → non-root on deployed server
        if file_check_failed:
            try:
                if SERVER_CREDS_DIR.is_dir():
                    warn("Running as non-root on the server. Using sudo for commands.")
                    self.local_mode = True
                    self.needs_sudo = True
                    return True
            except (PermissionError, OSError):
                pass

        return False

    def fetch_credentials(self, local_creds_dir: Path) -> bool:
        """Fetch credentials from server's /etc/meridian/ via SCP.

        In local mode (root), copies directly from /etc/meridian/.
        In remote mode, uses SCP for root or SSH+sudo for non-root users
        (SCP can't read root-owned /etc/meridian/ without sudo).
        """
        if self.local_mode:
            return self._copy_local_credentials(local_creds_dir)

        local_creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        if self.user != "root":
            # Non-root: SCP can't read root-owned /etc/meridian/.
            # Use SSH + sudo cat instead (conn.run() adds sudo automatically).
            result = self.run("cat /etc/meridian/proxy.yml", timeout=30)
            if result.returncode == 0 and result.stdout:
                dst = local_creds_dir / "proxy.yml"
                dst.write_text(result.stdout, encoding="utf-8")
                dst.chmod(0o600)
                return True
            return False

        try:
            result = subprocess.run(
                [
                    "scp",
                    *self._scp_opts,
                    f"{self.user}@{self._scp_host}:/etc/meridian/proxy.yml",
                    str(local_creds_dir / "proxy.yml"),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                (local_creds_dir / "proxy.yml").chmod(0o600)
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def write_file(self, local_path: Path, remote_path: str) -> bool:
        """Write a local file to the server, using sudo for non-root users.

        SCP can't write to root-owned directories (like /etc/meridian/) as a
        non-root user.  This method uses SSH + sudo tee instead.
        For root, plain SCP is used.
        """
        if self.local_mode:
            dst = Path(remote_path)
            if dst == local_path:
                return True
            if self.needs_sudo or self.user != "root":
                try:
                    result = subprocess.run(
                        ["sudo", "-n", "tee", remote_path],
                        input=local_path.read_bytes(),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        timeout=15,
                    )
                    if result.returncode != 0:
                        return False
                    subprocess.run(
                        ["sudo", "-n", "chmod", "600", remote_path],
                        capture_output=True,
                        timeout=5,
                        stdin=subprocess.DEVNULL,
                    )
                    return True
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    return False
            try:
                shutil.copy2(str(local_path), str(dst))
                dst.chmod(0o600)
                return True
            except (PermissionError, OSError):
                return False

        if self.user != "root":
            # Non-root: pipe file content through SSH with sudo tee
            q_path = shlex.quote(remote_path)
            remote_cmd = f"sudo -n tee {q_path} > /dev/null"
            try:
                result = subprocess.run(
                    ["ssh", *self._ssh_opts, f"{self.user}@{self.ip}", remote_cmd],
                    input=local_path.read_bytes(),
                    capture_output=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    chmod = self.run(f"chmod 600 {q_path}", timeout=5)
                    return chmod.returncode == 0
                return False
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                return False

        # Root: SCP works fine
        try:
            result = subprocess.run(
                [
                    "scp",
                    *self._scp_opts,
                    str(local_path),
                    f"{self.user}@{self._scp_host}:{remote_path}",
                ],
                capture_output=True,
                timeout=15,
                stdin=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
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


def tcp_connect(host: str, port: int, timeout: int = 5) -> bool:
    """Test TCP connectivity to host:port using a Python socket."""
    import socket as _socket

    try:
        conn = _socket.create_connection((host, port), timeout=timeout)
        conn.close()
        return True
    except (OSError, _socket.timeout):
        return False
