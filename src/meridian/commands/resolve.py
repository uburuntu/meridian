"""Server resolution logic shared across commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meridian.config import CREDS_BASE, SERVER_CREDS_DIR
from meridian.console import err_console, fail, info
from meridian.credentials import ServerCredentials
from meridian.servers import ServerRegistry
from meridian.ssh import ServerConnection


@dataclass
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
    """Check if /etc/meridian/proxy.yml exists and extract exit_ip."""
    proxy = SERVER_CREDS_DIR / "proxy.yml"
    if not proxy.exists():
        return None
    creds = ServerCredentials.load(proxy)
    return creds.exit_ip or None


def resolve_server(
    registry: ServerRegistry,
    requested_server: str = "",
    explicit_ip: str = "",
    user: str = "root",
) -> ResolvedServer:
    """Resolve which server to target.

    Priority: explicit IP > --server flag > local mode > single registered > fail.

    Args:
        registry: The server registry to search.
        requested_server: Value of --server flag (IP or name).
        explicit_ip: Positional IP argument from the command.
        user: SSH user (default root).

    Returns:
        ResolvedServer with all fields populated.

    Raises:
        typer.Exit: via fail() if resolution is impossible.
    """
    ip = ""
    local_mode = False

    # 1. Explicit IP argument takes highest priority
    if explicit_ip:
        ip = explicit_ip

    # 2. --server flag (resolve via registry)
    elif requested_server:
        entry = registry.find(requested_server)
        if entry:
            ip = entry.host
            user = entry.user
        elif _is_ipv4(requested_server):
            ip = requested_server
        else:
            fail(f"Server '{requested_server}' not found. Run: meridian server list")

    # 3. Running on the server itself — /etc/meridian/ exists
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
            user = entry.user
            label = f"{entry.name} ({ip})" if entry.name else ip
            info(f"Using server: {label}")

        elif registry.count() > 1:
            err_console.print("\n  Multiple servers. Use [bold]--server NAME[/bold]:\n")
            for entry in registry.list():
                label = entry.name or entry.host
                err_console.print(f"    [info]{label:<15s}[/info]  {entry.host}  ({entry.user})")
            err_console.print()
            fail("Specify a server with --server")

        else:
            # 0 servers — caller should handle this
            fail("No servers configured. Run: meridian setup")

    # Determine creds_dir
    if local_mode:
        creds_dir = SERVER_CREDS_DIR
    else:
        creds_dir = CREDS_BASE / ip

    conn = ServerConnection(ip=ip, user=user, local_mode=local_mode)

    return ResolvedServer(
        ip=ip,
        user=user,
        local_mode=local_mode,
        creds_dir=creds_dir,
        conn=conn,
    )


def ensure_server_connection(resolved: ResolvedServer) -> None:
    """Detect local mode if not already set, then verify SSH connectivity."""
    if not resolved.local_mode:
        if resolved.conn.detect_local_mode():
            resolved.local_mode = True
            resolved.creds_dir = SERVER_CREDS_DIR
    resolved.conn.check_ssh()


def fetch_credentials(resolved: ResolvedServer) -> bool:
    """Fetch credentials from server if not available locally."""
    proxy_file = resolved.creds_dir / "proxy.yml"
    if proxy_file.exists():
        return True
    resolved.creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return resolved.conn.fetch_credentials(resolved.creds_dir)


def _is_ipv4(s: str) -> bool:
    """Check if string looks like an IPv4 address."""
    parts = s.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
