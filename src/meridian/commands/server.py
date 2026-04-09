"""Server management — add, list, remove known servers."""

from __future__ import annotations

import shutil

from meridian.config import CREDS_BASE, SERVERS_FILE, sanitize_ip_for_path
from meridian.console import err_console, fail, info, line, ok, warn
from meridian.servers import ServerEntry, ServerRegistry
from meridian.ssh import ServerConnection, SSHError


def run_add(ip: str, name: str = "", user: str = "root") -> None:
    """Register a server, verify SSH, and fetch credentials."""
    if name and not _valid_name(name):
        fail("Server name must be alphanumeric (hyphens and underscores allowed)", hint_type="user")

    registry = ServerRegistry(SERVERS_FILE)
    conn = ServerConnection(ip=ip, user=user, local_mode=False)

    info(f"Connecting to {ip}...")
    try:
        conn.check_ssh()
    except SSHError as exc:
        fail(str(exc), hint=exc.hint, hint_type=exc.hint_type)

    # Fetch credentials from server
    creds_dir = CREDS_BASE / sanitize_ip_for_path(ip)
    creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if conn.fetch_credentials(creds_dir):
        ok("Fetched credentials from server")
    else:
        warn("No credentials found on server (run meridian deploy first)")

    registry.add(ServerEntry(host=ip, user=user, name=name))
    ok(f"Server added: {name or ip}")


def run_list() -> None:
    """Display all registered servers."""
    registry = ServerRegistry(SERVERS_FILE)
    entries = registry.list()

    if not entries:
        info("No servers configured. Run: meridian deploy IP")
        return

    err_console.print()
    err_console.print(f"  [bold]{'NAME':<15s}  {'IP':<39s}  {'USER':<8s}[/bold]")
    line()
    for entry in entries:
        label = entry.name if entry.name else "--"
        err_console.print(f"  {label:<15s}  {entry.host:<39s}  {entry.user:<8s}")
    err_console.print()


def run_remove(query: str) -> None:
    """Remove a server by IP or name, including local credentials."""
    registry = ServerRegistry(SERVERS_FILE)

    entry = registry.find(query)
    if not entry:
        fail(f"Server '{query}' not found", hint_type="user")

    host = entry.host
    registry.remove(query)

    # Remove local credentials
    creds_dir = CREDS_BASE / sanitize_ip_for_path(host)
    if creds_dir.exists():
        shutil.rmtree(creds_dir)

    ok(f"Server removed: {query}")


def _valid_name(name: str) -> bool:
    """Check that name is alphanumeric with hyphens/underscores."""
    if not name:
        return True
    if not name[0].isalnum():
        return False
    return all(c.isalnum() or c in "-_" for c in name)
