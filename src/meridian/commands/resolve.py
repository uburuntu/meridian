"""Server resolution logic shared across commands."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from meridian.config import CREDS_BASE, SERVER_CREDS_DIR, is_ipv4
from meridian.console import err_console, fail, info, warn
from meridian.credentials import ServerCredentials
from meridian.servers import ServerRegistry
from meridian.ssh import ServerConnection

LOCAL_KEYWORDS = ("local", "locally")

# Servers that have already shown a version mismatch warning this session
_warned_servers: set[str] = set()

_VALID_SSH_USER = re.compile(r"^[a-zA-Z0-9._-]+$")


def is_local_keyword(value: str) -> bool:
    """Check if a value is the 'local' keyword for on-server deployment."""
    return value.lower() in LOCAL_KEYWORDS


def detect_public_ip() -> str:
    """Detect the machine's public IPv4 address."""
    for url in ("https://ifconfig.me", "https://api.ipify.org"):
        try:
            result = subprocess.run(
                ["curl", "-4", "-s", "--max-time", "3", url],
                capture_output=True,
                text=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
            )
            ip = result.stdout.strip()
            if is_ipv4(ip):
                return ip
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return ""


@dataclass(frozen=True)
class ResolvedServer:
    """Result of server resolution — everything needed to interact with a server."""

    ip: str
    user: str
    local_mode: bool
    creds_dir: Path
    conn: ServerConnection

    @property
    def creds(self) -> ServerCredentials:
        """Load credentials from the resolved creds_dir."""
        return ServerCredentials.load(self.creds_dir / "proxy.yml")


def _detect_local_mode_from_creds() -> str | None:
    """Check if /etc/meridian/proxy.yml is readable and extract server IP.

    Only succeeds for root. Non-root users can't read /etc/meridian/
    and will use the remote SSH path instead.
    """
    proxy = SERVER_CREDS_DIR / "proxy.yml"
    try:
        if not proxy.is_file():
            return None
        creds = ServerCredentials.load(proxy)
        return creds.server.ip or None
    except (PermissionError, OSError):
        return None


def resolve_server(
    registry: ServerRegistry,
    requested_server: str = "",
    explicit_ip: str = "",
    user: str = "",
) -> ResolvedServer:
    """Resolve which server to target.

    Priority: explicit IP / 'local' keyword > --server flag > local mode (root) > single registered > fail.

    The 'local' keyword (or 'locally') triggers on-server deployment without SSH.

    If user is empty, it's auto-resolved from the server registry.
    If user is explicitly set, it overrides the registry value.
    """
    ip = ""
    registry_user = ""
    local_mode = False

    # 1. Explicit IP argument or 'local' keyword takes highest priority
    if explicit_ip:
        if is_local_keyword(explicit_ip):
            detected_ip = detect_public_ip()
            if not detected_ip:
                fail(
                    "Could not detect this server's public IP",
                    hint="Provide the IP explicitly: meridian deploy 1.2.3.4",
                    hint_type="system",
                )
            ip = detected_ip
            local_mode = True
            info(f"Local mode: deploying on this server ({ip})")
        else:
            ip = explicit_ip
            # Check registry for saved user
            entry = registry.find(explicit_ip)
            if entry:
                registry_user = entry.user

    # 2. --server flag (resolve via registry, or 'local' keyword)
    elif requested_server:
        if is_local_keyword(requested_server):
            detected_ip = detect_public_ip()
            if not detected_ip:
                fail(
                    "Could not detect this server's public IP",
                    hint="Provide the IP explicitly: meridian <command> 1.2.3.4",
                    hint_type="system",
                )
            ip = detected_ip
            local_mode = True
            info(f"Local mode: using this server ({ip})")
        else:
            entry = registry.find(requested_server)
            if entry:
                ip = entry.host
                registry_user = entry.user
            elif is_ipv4(requested_server):
                ip = requested_server
            else:
                fail(
                    f"Server '{requested_server}' not found",
                    hint="See registered servers: meridian server list",
                    hint_type="user",
                )

    # 3. Running on the server itself as root — /etc/meridian/ readable
    else:
        local_ip = _detect_local_mode_from_creds()
        if local_ip:
            ip = local_ip
            local_mode = True

        # 4. Single server auto-select
        elif registry.count() == 1:
            entries = registry.list()
            entry = entries[0]
            ip = entry.host
            registry_user = entry.user
            label = f"{entry.name} ({ip})" if entry.name else ip
            info(f"Using server: {label}")

        elif registry.count() > 1:
            err_console.print("\n  Multiple servers. Use [bold]--server NAME[/bold]:\n")
            for entry in registry.list():
                label = entry.name or entry.host
                err_console.print(f"    [info]{label:<15s}[/info]  {entry.host}  ({entry.user})")
            err_console.print()
            fail("Specify a server with --server", hint="Example: meridian <command> --server NAME", hint_type="user")

        else:
            fail("No servers configured", hint="Deploy a server first: meridian deploy IP", hint_type="user")

    # Resolve user: explicit flag > registry > default root
    resolved_user = user or registry_user or "root"

    if not _VALID_SSH_USER.match(resolved_user):
        fail(
            f"SSH user '{resolved_user}' is invalid",
            hint="Use letters, numbers, dots, hyphens, and underscores.",
            hint_type="user",
        )

    # Determine creds_dir
    if local_mode:
        creds_dir = SERVER_CREDS_DIR
    else:
        creds_dir = CREDS_BASE / ip

    conn = ServerConnection(ip=ip, user=resolved_user, local_mode=local_mode)

    return ResolvedServer(
        ip=ip,
        user=resolved_user,
        local_mode=local_mode,
        creds_dir=creds_dir,
        conn=conn,
    )


def ensure_server_connection(resolved: ResolvedServer) -> ResolvedServer:
    """Detect local mode if not already set, then verify SSH connectivity.

    Local mode activates for root (who can read /etc/meridian/) and for
    non-root users (who use sudo for commands). Non-root users keep
    creds_dir in their home directory (sudo copies from /etc/meridian/).

    Returns a new ResolvedServer with updated local_mode/creds_dir if changed.
    """
    if not resolved.local_mode:
        if resolved.conn.detect_local_mode():
            if not resolved.conn.needs_sudo:
                # Root on server — read /etc/meridian/ directly
                new_creds_dir = SERVER_CREDS_DIR
            else:
                # Non-root on server — use user-local creds dir
                new_creds_dir = CREDS_BASE / resolved.ip
            resolved = ResolvedServer(
                ip=resolved.ip,
                user=resolved.user,
                local_mode=True,
                creds_dir=new_creds_dir,
                conn=resolved.conn,
            )
    resolved.conn.check_ssh()
    return resolved


def fetch_credentials(resolved: ResolvedServer) -> bool:
    """Fetch credentials from server if not available locally."""
    proxy_file = resolved.creds_dir / "proxy.yml"
    try:
        if proxy_file.is_file():
            _check_version_mismatch(resolved.ip, proxy_file)
            return True
    except (PermissionError, OSError):
        pass
    try:
        resolved.creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError:
        return False
    ok = resolved.conn.fetch_credentials(resolved.creds_dir)
    if ok:
        _check_version_mismatch(resolved.ip, proxy_file)
    return ok


def _check_version_mismatch(server_ip: str, proxy_file: Path) -> None:
    """Warn once per session if the server was deployed with a different CLI version."""
    if server_ip in _warned_servers:
        return

    creds = ServerCredentials.load(proxy_file)
    deployed_with = creds.server.deployed_with
    if not deployed_with:
        return  # Legacy credentials — no version info

    from meridian import __version__

    try:
        from packaging.version import Version

        deployed = Version(deployed_with)
        current = Version(__version__)
    except Exception:
        return  # Unparseable version — skip silently

    if deployed.major == current.major and deployed.minor == current.minor:
        return  # Patch differences are fine

    _warned_servers.add(server_ip)
    err_console.print()
    warn("Version mismatch")
    err_console.print(
        f"    Server deployed with Meridian [bold]{deployed_with}[/bold] — you're running [bold]{__version__}[/bold]."
    )
    err_console.print()
    err_console.print("    To update the server:")
    err_console.print(f"      [info]meridian deploy {server_ip}[/info]       Re-provisions configs (nginx, services)")
    err_console.print(f"      [info]meridian teardown {server_ip}[/info]    Full reset (then re-deploy from scratch)")
    err_console.print()
    err_console.print("    To match the server instead:")
    err_console.print(f"      [info]uv tool install meridian-vpn=={deployed_with}[/info]")
    err_console.print()
