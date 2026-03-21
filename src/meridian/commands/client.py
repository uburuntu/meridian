"""Client management — add, list, remove proxy clients."""

from __future__ import annotations

import json
import shlex

from meridian.ansible import ensure_ansible, ensure_collections, get_playbooks_dir, run_playbook
from meridian.commands.resolve import (
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import SERVERS_FILE
from meridian.console import err_console, fail, info
from meridian.credentials import ServerCredentials
from meridian.servers import ServerRegistry


def run_add(
    name: str,
    user: str = "root",
    requested_server: str = "",
) -> None:
    """Add a new client to the proxy server."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)

    ensure_ansible()
    playbooks_dir = get_playbooks_dir()
    ensure_collections(playbooks_dir)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    info(f"Adding client '{name}'...")
    err_console.print()

    rc = run_playbook(
        "playbook-client.yml",
        ip=resolved.ip,
        creds_dir=resolved.creds_dir,
        extra_vars={"client_action": "add", "client_name": name},
        local_mode=resolved.local_mode,
        user=resolved.user,
    )
    if rc != 0:
        fail(f"Failed to add client '{name}'")

    # Show result
    html_files = list(resolved.creds_dir.glob(f"*-{name}-connection-info.html"))
    if html_files:
        err_console.print("\n  [ok][bold]Done![/bold][/ok]\n")
        err_console.print(f"  Send this file to {name}:")
        err_console.print(f"     [bold]{html_files[0]}[/bold]")
        err_console.print("     [dim](They open it, scan the QR code, and connect)[/dim]\n")
        err_console.print(f"  [dim]Test reachability: meridian ping {resolved.ip}[/dim]")
        err_console.print("  [dim]View all clients:  meridian client list[/dim]\n")


def run_list(
    user: str = "root",
    requested_server: str = "",
) -> None:
    """List all clients via direct panel API query (no Ansible)."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    proxy_file = resolved.creds_dir / "proxy.yml"
    if not proxy_file.exists():
        fail("No credentials found. Run: meridian setup")

    creds = ServerCredentials.load(proxy_file)
    if not creds.has_credentials:
        fail("No panel credentials found. Run: meridian setup")

    panel_port = 2053
    panel_user = creds.panel_username
    panel_pass = creds.panel_password
    panel_path = creds.panel_web_base_path

    # Build the curl commands for login + list
    q_user = shlex.quote(panel_user)
    q_pass = shlex.quote(panel_pass)
    q_path = shlex.quote(panel_path)
    q_port = shlex.quote(str(panel_port))
    cookie = "$HOME/.meridian/.cookie"
    login_cmd = (
        f"mkdir -p $HOME/.meridian && "
        f"curl -s -c {cookie}"
        f" -d username={q_user}'&'password={q_pass}"
        f" http://127.0.0.1:{q_port}/{q_path}/login > /dev/null && "
        f"curl -s -b {cookie}"
        f" http://127.0.0.1:{q_port}/{q_path}/panel/api/inbounds/list; "
        f"rm -f {cookie}"
    )

    result = resolved.conn.run(login_cmd, timeout=15)
    if result.returncode != 0:
        fail("Failed to connect to panel API")

    raw_json = result.stdout.strip()
    if not raw_json:
        fail("Empty response from panel API")

    _display_client_list(raw_json)


def run_remove(
    name: str,
    user: str = "root",
    requested_server: str = "",
) -> None:
    """Remove a client from the proxy server."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, user=user)

    ensure_ansible()
    playbooks_dir = get_playbooks_dir()
    ensure_collections(playbooks_dir)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    info(f"Removing client '{name}'...")
    err_console.print()

    rc = run_playbook(
        "playbook-client.yml",
        ip=resolved.ip,
        creds_dir=resolved.creds_dir,
        extra_vars={"client_action": "remove", "client_name": name},
        local_mode=resolved.local_mode,
        user=resolved.user,
    )
    if rc != 0:
        fail(f"Failed to remove client '{name}'")


def _display_client_list(raw_json: str) -> None:
    """Parse panel API JSON response and display client list."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        fail("Invalid JSON response from panel API")

    if not data.get("success"):
        fail("Panel API error")

    inbounds = data.get("obj", [])

    # Build lookup: inbound remark -> set of client emails
    clients_by_inbound: dict[str, set[str]] = {}
    for ib in inbounds:
        remark = ib.get("remark", "")
        settings = json.loads(ib.get("settings", "{}"))
        emails = {c.get("email", "") for c in settings.get("clients", [])}
        clients_by_inbound[remark] = emails

    # Reality clients are the canonical list
    reality_clients: list[dict] = []
    for ib in inbounds:
        if ib.get("remark") == "VLESS-Reality":
            settings = json.loads(ib.get("settings", "{}"))
            reality_clients = settings.get("clients", [])
            break

    wss_emails = clients_by_inbound.get("VLESS-WSS", set())
    xhttp_emails = clients_by_inbound.get("VLESS-Reality-XHTTP", set())

    err_console.print()
    err_console.print("  ======================================================================")
    err_console.print("                        PROXY CLIENTS")
    err_console.print("  ======================================================================")
    err_console.print()
    err_console.print("    Name              Status     Protocols")
    err_console.print("    " + "\u2500" * 49)

    for c in reality_clients:
        email = c.get("email", "")
        name = email.removeprefix("reality-") if email.startswith("reality-") else email
        status = "active" if c.get("enable", True) else "disabled"
        protos = ["Reality"]
        if f"xhttp-{name}" in xhttp_emails:
            protos.append("XHTTP")
        if f"wss-{name}" in wss_emails:
            protos.append("WSS")
        err_console.print(f"    {name:<17s} {status:<10s} {' + '.join(protos)}")

    err_console.print()
    err_console.print("    " + "\u2500" * 49)
    count = len(reality_clients)
    suffix = "s" if count != 1 else ""
    err_console.print(f"    Total: {count} client{suffix}")
    err_console.print()
    err_console.print("  ======================================================================")
    err_console.print()
    err_console.print("  [dim]Add: meridian client add NAME  |  Remove: meridian client remove NAME[/dim]")
    err_console.print()
