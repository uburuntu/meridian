"""Remove proxy from server."""

from __future__ import annotations

import shutil

import typer

from meridian.ansible import ensure_ansible, ensure_collections, get_playbooks_dir, run_playbook
from meridian.commands.resolve import (
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import CREDS_BASE, SERVERS_FILE
from meridian.console import err_console, fail, info, prompt, warn
from meridian.servers import ServerRegistry


def run(
    ip: str = "",
    user: str = "root",
    yes: bool = False,
    requested_server: str = "",
) -> None:
    """Uninstall Meridian from a server."""
    registry = ServerRegistry(SERVERS_FILE)

    # If no IP given and resolution fails, prompt for it
    if not ip:
        try:
            resolved = resolve_server(registry, requested_server=requested_server, user=user)
        except SystemExit:
            server_ip = prompt("Server IP to uninstall from")
            if not server_ip:
                fail("Server IP is required for uninstall")
            resolved = resolve_server(registry, explicit_ip=server_ip, user=user)
    else:
        resolved = resolve_server(registry, requested_server=requested_server, explicit_ip=ip, user=user)

    # Confirmation
    err_console.print()
    warn(f"This will remove Meridian from {resolved.ip}.")
    warn("Docker and system packages will NOT be touched.")
    err_console.print()

    if not yes:
        answer = prompt("Continue? (y/N)")
        if answer.lower() != "y":
            info("Cancelled.")
            raise typer.Exit()
    err_console.print()

    # Prepare: ensure ansible, detect local mode, check SSH
    ensure_ansible()
    playbooks_dir = get_playbooks_dir()
    ensure_collections(playbooks_dir)

    ensure_server_connection(resolved)
    fetch_credentials(resolved)

    info(f"Removing Meridian from {resolved.ip}...")
    err_console.print()

    rc = run_playbook(
        "playbook-uninstall.yml",
        ip=resolved.ip,
        creds_dir=resolved.creds_dir,
        local_mode=resolved.local_mode,
        user=resolved.user,
    )
    if rc != 0:
        fail("Uninstall playbook failed")

    # Remove from server registry
    registry.remove(resolved.ip)

    # Remove local credentials
    creds_dir = CREDS_BASE / resolved.ip
    if creds_dir.exists():
        shutil.rmtree(creds_dir)

    err_console.print("\n  [ok][bold]Uninstall complete.[/bold][/ok]\n")
