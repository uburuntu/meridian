"""Relay management — deploy, list, remove, check relay nodes."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone

import yaml

from meridian.commands.resolve import (
    ResolvedServer,
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import CREDS_BASE, RELAY_SERVICE_NAME, SERVERS_FILE, is_ipv4
from meridian.console import confirm, err_console, fail, info, line, ok, warn
from meridian.credentials import RelayEntry, ServerCredentials
from meridian.servers import ServerEntry, ServerRegistry
from meridian.ssh import SSH_OPTS, ServerConnection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_exit(
    registry: ServerRegistry,
    exit_arg: str,
    user: str,
) -> ResolvedServer:
    """Resolve and validate the exit server."""
    if is_ipv4(exit_arg):
        resolved = resolve_server(registry, explicit_ip=exit_arg, user=user)
    else:
        resolved = resolve_server(registry, requested_server=exit_arg, user=user)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    # Verify exit is deployed
    proxy_file = resolved.creds_dir / "proxy.yml"
    if not proxy_file.exists():
        fail(
            "Exit server is not deployed",
            hint=f"Deploy it first: meridian deploy {resolved.ip}",
            hint_type="user",
        )

    creds = ServerCredentials.load(proxy_file)
    if not creds.has_credentials:
        fail(
            "Exit server has no panel credentials",
            hint=f"Deploy it first: meridian deploy {resolved.ip}",
            hint_type="user",
        )

    return resolved


def _find_exit_for_relay(relay_ip: str) -> tuple[ServerRegistry, ResolvedServer] | None:
    """Find which exit server a relay belongs to by scanning credentials."""
    registry = ServerRegistry(SERVERS_FILE)
    for entry in registry.list():
        creds_dir = CREDS_BASE / entry.host
        proxy_file = creds_dir / "proxy.yml"
        if not proxy_file.exists():
            continue
        creds = ServerCredentials.load(proxy_file)
        for relay in creds.relays:
            if relay.ip == relay_ip:
                resolved = resolve_server(registry, explicit_ip=entry.host, user=entry.user)
                resolved = ensure_server_connection(resolved)
                fetch_credentials(resolved)
                return registry, resolved
    return None


def _save_relay_local(relay_ip: str, exit_ip: str, exit_port: int, listen_port: int) -> None:
    """Save relay metadata to ~/.meridian/credentials/<relay-ip>/relay.yml."""
    import os
    import tempfile

    relay_creds_dir = CREDS_BASE / relay_ip
    relay_creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    relay_meta = {
        "role": "relay",
        "exit_ip": exit_ip,
        "exit_port": exit_port,
        "listen_port": listen_port,
    }
    relay_file = relay_creds_dir / "relay.yml"
    # Atomic write: tempfile + rename
    fd, tmp = tempfile.mkstemp(dir=str(relay_creds_dir), suffix=".tmp")
    try:
        os.write(fd, yaml.dump(relay_meta, default_flow_style=False, sort_keys=False).encode())
        os.close(fd)
        fd = -1
        os.chmod(tmp, 0o600)
        os.rename(tmp, str(relay_file))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _sync_exit_credentials_to_server(resolved_exit: ResolvedServer) -> None:
    """Sync exit server credentials back to /etc/meridian/ after relay changes."""
    if resolved_exit.local_mode:
        return
    try:
        subprocess.run(
            [
                "scp",
                *SSH_OPTS,
                "-r",
                f"{resolved_exit.creds_dir}/",
                f"{resolved_exit.user}@{resolved_exit.ip}:/etc/meridian/",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        warn("Could not sync credentials to exit server")


def _regenerate_client_pages(
    resolved_exit: ResolvedServer,
    creds: ServerCredentials,
) -> None:
    """Regenerate connection pages for all clients after relay topology change."""
    from meridian.render import render_hosted_html, save_connection_html, save_connection_text
    from meridian.urls import build_all_relay_urls, build_protocol_urls, generate_qr_base64

    for client in creds.clients:
        protocol_urls = build_protocol_urls(
            name=client.name,
            reality_uuid=client.reality_uuid,
            wss_uuid=client.wss_uuid,
            creds=creds,
        )
        relay_url_sets = build_all_relay_urls(client.name, client.reality_uuid, client.wss_uuid, creds)

        server_ip = creds.server.ip or resolved_exit.ip
        domain = creds.server.domain or ""
        file_prefix = f"{resolved_exit.ip}-{client.name}"

        # Regenerate local files
        save_connection_text(
            protocol_urls,
            resolved_exit.creds_dir / f"{file_prefix}-connection-info.txt",
            server_ip,
            client_name=client.name,
            relay_entries=relay_url_sets,
        )
        save_connection_html(
            protocol_urls,
            resolved_exit.creds_dir / f"{file_prefix}-connection-info.html",
            server_ip,
            domain=domain,
            client_name=client.name,
            relay_entries=relay_url_sets,
        )

        # Regenerate server-hosted page (if enabled)
        if creds.server.hosted_page and creds.panel.info_page_path and client.reality_uuid:
            import shlex
            from dataclasses import replace as dc_replace

            urls_with_qr = [dc_replace(p, qr_b64=generate_qr_base64(p.url)) if p.url else p for p in protocol_urls]

            html = render_hosted_html(
                urls_with_qr,
                server_ip=server_ip,
                domain=domain,
                client_name=client.name,
                relay_entries=relay_url_sets,
            )

            conn = resolved_exit.conn
            q_uuid = shlex.quote(client.reality_uuid)
            q_html = shlex.quote(html)
            conn.run(
                f"mkdir -p /var/www/private/{q_uuid} && "
                f"printf '%s' {q_html} > /var/www/private/{q_uuid}/index.html && "
                f"chown caddy:caddy /var/www/private/{q_uuid}/index.html",
                timeout=15,
            )


# ---------------------------------------------------------------------------
# Relay Deploy
# ---------------------------------------------------------------------------


def run_deploy(
    relay_ip: str,
    exit_arg: str,
    user: str = "root",
    relay_name: str = "",
    listen_port: int = 443,
    yes: bool = False,
) -> None:
    """Deploy a relay node that forwards traffic to an exit server."""
    # Validate relay IP
    if not is_ipv4(relay_ip):
        fail(f"Invalid relay IP: {relay_ip}", hint="Enter a valid IPv4 address", hint_type="user")

    if relay_name and not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", relay_name):
        fail(f"Invalid relay name: {relay_name}", hint="Use letters, numbers, hyphens, underscores", hint_type="user")

    registry = ServerRegistry(SERVERS_FILE)

    # --- Explain what a relay does ---
    err_console.print()
    err_console.print("  [bold]What is a relay?[/bold]")
    err_console.print("  [dim]A relay is a lightweight server inside your country that forwards[/dim]")
    err_console.print("  [dim]traffic to an exit server abroad. Censors see only domestic traffic.[/dim]")
    err_console.print("  [dim]The relay runs Realm (a fast TCP forwarder) — no VPN software needed.[/dim]")
    err_console.print("  [dim]All encryption remains end-to-end between client and exit server.[/dim]")
    err_console.print()

    # Resolve exit server
    info(f"Resolving exit server: {exit_arg}")
    resolved_exit = _resolve_exit(registry, exit_arg, user)
    exit_creds = ServerCredentials.load(resolved_exit.creds_dir / "proxy.yml")

    # Check if relay already registered
    for relay in exit_creds.relays:
        if relay.ip == relay_ip:
            fail(
                f"Relay {relay_ip} is already attached to exit {resolved_exit.ip}",
                hint=f"To re-deploy, remove first: meridian relay remove {relay_ip} --exit {resolved_exit.ip}",
                hint_type="user",
            )

    # Same-server warning (exit and relay on same IP)
    if relay_ip == resolved_exit.ip:
        if listen_port == 443:
            fail(
                "Relay and exit are the same server — port 443 is already in use by the exit",
                hint="Use a different port: meridian relay deploy "
                f"{relay_ip} --exit {resolved_exit.ip} --port 8443\n"
                "  This is useful for testing but not for production.",
                hint_type="user",
            )
        warn(
            f"Relay and exit are the same server ({relay_ip}). "
            "This is fine for testing but won't bypass IP blocks in production."
        )

    ok(f"Exit server verified: {resolved_exit.ip}")

    # Connect to relay server
    info(f"Connecting to relay server: {relay_ip}")
    relay_conn = ServerConnection(ip=relay_ip, user=user)
    relay_conn.check_ssh()
    ok("SSH connection to relay established")

    # Check if relay port is already in use
    port_check = relay_conn.run(f"ss -tlnp sport = :{listen_port} 2>/dev/null", timeout=10)
    if port_check.returncode == 0 and f":{listen_port}" in port_check.stdout:
        # Extract process name from ss output for a helpful message
        ss_lines = port_check.stdout.strip().splitlines()
        process_info = ""
        for ss_line in ss_lines[1:]:  # skip header
            if f":{listen_port}" in ss_line:
                if "users:" in ss_line:
                    process_info = ss_line.split("users:")[1].strip().strip("()")
                break
        msg = f"Port {listen_port} is already in use"
        if process_info:
            msg += f" by {process_info}"
        fail(
            msg,
            hint=f"Choose a different port: meridian relay deploy {relay_ip} --exit {exit_arg} --port <OTHER_PORT>",
            hint_type="system",
        )

    # Test relay -> exit connectivity (exit always listens on 443)
    import shlex

    info("Testing relay -> exit connectivity...")
    q_exit_ip = shlex.quote(resolved_exit.ip)
    tcp_test = relay_conn.run(
        f"bash -c 'echo > /dev/tcp/{q_exit_ip}/443' 2>/dev/null",
        timeout=10,
    )
    if tcp_test.returncode != 0:
        warn(f"Relay cannot reach exit {resolved_exit.ip}:443 — will attempt deployment anyway")
    else:
        ok("Relay -> exit connectivity confirmed")

    # Show deployment summary
    from rich.panel import Panel

    from meridian.config import REALM_VERSION

    summary = (
        f"Relay:    {user}@{relay_ip}:{listen_port}\n"
        f"Exit:     {resolved_exit.ip}:443\n"
        f"Engine:   Realm v{REALM_VERSION} (zero-copy TCP forwarder)\n"
        f"Name:     {relay_name or '(auto)'}\n"
        f"\n"
        f"How it works:\n"
        f"  Client -> {relay_ip}:{listen_port} -> "
        f"{resolved_exit.ip}:443 -> Internet\n"
        f"  Censors see: domestic traffic to {relay_ip}\n"
        f"  Encryption: end-to-end (relay cannot read content)"
    )
    err_console.print()
    err_console.print(Panel(summary, title="[bold]Relay deployment plan[/bold]", border_style="cyan", padding=(0, 2)))
    err_console.print()

    if not yes:
        confirm(f"Deploy relay to {user}@{relay_ip}?")
    err_console.print()

    # Run relay provisioner
    from meridian.provision.relay import RelayContext, build_relay_steps
    from meridian.provision.steps import Provisioner

    ctx = RelayContext(
        relay_ip=relay_ip,
        exit_ip=resolved_exit.ip,
        exit_port=443,
        listen_port=listen_port,
        user=user,
    )

    info(f"Configuring relay at {relay_ip}...")
    err_console.print()

    provisioner = Provisioner(build_relay_steps(ctx))
    results = provisioner.run(relay_conn, ctx)

    # Check for failures
    failed = [r for r in results if r.status == "failed"]
    if failed:
        fail(
            "Relay deployment failed",
            hint=f"Step '{failed[0].name}' failed: {failed[0].detail}",
            hint_type="system",
        )

    err_console.print()
    ok("Relay deployed successfully")

    # Update exit credentials with new relay entry
    relay_entry = RelayEntry(
        ip=relay_ip,
        name=relay_name,
        port=listen_port,
        added=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    exit_creds.relays.append(relay_entry)
    exit_creds.save(resolved_exit.creds_dir / "proxy.yml")

    # Sync credentials to exit server
    _sync_exit_credentials_to_server(resolved_exit)

    # Save relay metadata locally
    _save_relay_local(relay_ip, resolved_exit.ip, 443, listen_port)

    # Register relay in server registry
    registry.add(ServerEntry(host=relay_ip, user=user, name=relay_name))

    # Regenerate connection pages for all existing clients
    if exit_creds.clients:
        info("Regenerating client connection pages...")
        _regenerate_client_pages(resolved_exit, exit_creds)
        ok(f"Updated {len(exit_creds.clients)} client page(s)")

    # Print success
    err_console.print()
    err_console.print("  [ok][bold]Done![/bold][/ok]")
    err_console.print()
    ok(f"Relay {relay_ip} is forwarding to exit {resolved_exit.ip}")
    err_console.print()

    err_console.print("  [bold]How clients connect now:[/bold]")
    err_console.print(
        f"  [dim]Client -> {relay_ip}:{listen_port} (domestic) -> {resolved_exit.ip}:443 (abroad) -> Internet[/dim]"
    )
    err_console.print(f"  [dim]Censors only see traffic to {relay_ip} — a domestic IP.[/dim]")
    err_console.print()

    err_console.print("  [bold]What changed for existing clients:[/bold]")
    if exit_creds.clients:
        n = len(exit_creds.clients)
        err_console.print(f"  [dim]All {n} client page(s) now show relay connection as recommended.[/dim]")
        err_console.print("  [dim]Direct connection URLs are still available as backup.[/dim]")
    else:
        err_console.print("  [dim]No clients yet. When you add them, relay URLs will be included automatically.[/dim]")
    err_console.print()

    err_console.print("  [bold]Next steps:[/bold]\n")
    err_console.print("  [ok]1.[/ok] Add a client (relay URLs included automatically):")
    err_console.print(f"     [info]meridian client add alice --server {resolved_exit.ip}[/info]\n")
    err_console.print("  [ok]2.[/ok] Check relay health:")
    err_console.print(f"     [info]meridian relay check {relay_ip}[/info]\n")
    err_console.print("  [ok]3.[/ok] List all relays:")
    err_console.print("     [info]meridian relay list[/info]\n")
    err_console.print()
    line()


# ---------------------------------------------------------------------------
# Relay List
# ---------------------------------------------------------------------------


def run_list(
    exit_arg: str = "",
    user: str = "",
) -> None:
    """List relay nodes attached to exit server(s)."""
    from rich.box import ROUNDED
    from rich.table import Table

    registry = ServerRegistry(SERVERS_FILE)

    if exit_arg:
        # List relays for a specific exit
        resolved = _resolve_exit(registry, exit_arg, user)
        creds = ServerCredentials.load(resolved.creds_dir / "proxy.yml")

        if not creds.relays:
            info(f"No relays attached to {resolved.ip}")
            err_console.print(f"\n  [dim]Add one: meridian relay deploy RELAY_IP --exit {resolved.ip}[/dim]\n")
            return

        table = Table(
            title=f"Relays for {resolved.ip}",
            show_lines=False,
            pad_edge=False,
            box=ROUNDED,
            padding=(0, 2),
        )
        table.add_column("IP", style="bold cyan")
        table.add_column("Name", style="dim")
        table.add_column("Port", justify="right")
        table.add_column("Added", style="dim")

        for relay in creds.relays:
            table.add_row(relay.ip, relay.name or "-", str(relay.port), relay.added[:10])

        err_console.print()
        err_console.print(table)
        err_console.print()
        err_console.print(f"  [dim]Total: {len(creds.relays)} relay(s)[/dim]\n")
        return

    # List all relays across all exits
    all_relays: list[tuple[str, RelayEntry]] = []
    for entry in registry.list():
        creds_dir = CREDS_BASE / entry.host
        proxy_file = creds_dir / "proxy.yml"
        if not proxy_file.exists():
            continue
        creds = ServerCredentials.load(proxy_file)
        for relay in creds.relays:
            all_relays.append((entry.host, relay))

    if not all_relays:
        info("No relay nodes configured")
        err_console.print("\n  [dim]Deploy one: meridian relay deploy RELAY_IP --exit EXIT_IP[/dim]\n")
        return

    table = Table(
        title="All Relay Nodes",
        show_lines=False,
        pad_edge=False,
        box=ROUNDED,
        padding=(0, 2),
    )
    table.add_column("Relay IP", style="bold cyan")
    table.add_column("Name", style="dim")
    table.add_column("Exit IP", style="bold")
    table.add_column("Port", justify="right")
    table.add_column("Added", style="dim")

    for exit_ip, relay in all_relays:
        table.add_row(relay.ip, relay.name or "-", exit_ip, str(relay.port), relay.added[:10])

    err_console.print()
    err_console.print(table)
    err_console.print()
    err_console.print(f"  [dim]Total: {len(all_relays)} relay(s)[/dim]\n")


# ---------------------------------------------------------------------------
# Relay Remove
# ---------------------------------------------------------------------------


def run_remove(
    relay_ip: str,
    exit_arg: str = "",
    user: str = "",
    yes: bool = False,
) -> None:
    """Remove a relay node."""
    if not is_ipv4(relay_ip):
        fail(f"Invalid relay IP: {relay_ip}", hint="Enter a valid IPv4 address", hint_type="user")

    registry = ServerRegistry(SERVERS_FILE)

    # Find the exit server for this relay
    if exit_arg:
        resolved_exit = _resolve_exit(registry, exit_arg, user)
    else:
        result = _find_exit_for_relay(relay_ip)
        if result is None:
            fail(
                f"Relay {relay_ip} not found in any exit server's configuration",
                hint="Specify exit with --exit, or check: meridian relay list",
                hint_type="user",
            )
        registry, resolved_exit = result

    exit_creds = ServerCredentials.load(resolved_exit.creds_dir / "proxy.yml")

    # Find relay entry
    relay_entry = next((r for r in exit_creds.relays if r.ip == relay_ip), None)
    if relay_entry is None:
        fail(
            f"Relay {relay_ip} is not attached to exit {resolved_exit.ip}",
            hint="Check: meridian relay list",
            hint_type="user",
        )

    if not yes:
        relay_label = relay_entry.name or relay_ip
        confirm(f"Remove relay {relay_label} from exit {resolved_exit.ip}?")

    # Stop service on relay
    info(f"Stopping relay service on {relay_ip}...")
    try:
        relay_conn = ServerConnection(ip=relay_ip, user=user or "root")
        relay_conn.check_ssh()
        relay_conn.run(f"systemctl stop {RELAY_SERVICE_NAME} 2>/dev/null", timeout=15)
        relay_conn.run(f"systemctl disable {RELAY_SERVICE_NAME} 2>/dev/null", timeout=10)
        ok("Relay service stopped")
    except Exception:
        warn(f"Could not connect to relay {relay_ip} — service may still be running")

    # Remove relay from exit credentials
    exit_creds.relays = [r for r in exit_creds.relays if r.ip != relay_ip]
    exit_creds.save(resolved_exit.creds_dir / "proxy.yml")
    ok(f"Relay {relay_ip} removed from exit configuration")

    # Sync credentials to exit server
    _sync_exit_credentials_to_server(resolved_exit)

    # Clean up local relay credentials
    relay_creds_dir = CREDS_BASE / relay_ip
    relay_file = relay_creds_dir / "relay.yml"
    if relay_file.exists():
        relay_file.unlink()

    # Remove from server registry
    registry.remove(relay_ip)

    # Regenerate connection pages
    if exit_creds.clients:
        info("Regenerating client connection pages...")
        _regenerate_client_pages(resolved_exit, exit_creds)
        ok(f"Updated {len(exit_creds.clients)} client page(s)")

    err_console.print(f"\n  Relay {relay_ip} has been removed.\n")


# ---------------------------------------------------------------------------
# Relay Check
# ---------------------------------------------------------------------------


def run_check(
    relay_ip: str,
    exit_arg: str = "",
    user: str = "",
) -> None:
    """Check health of a relay node."""
    if not is_ipv4(relay_ip):
        fail(f"Invalid relay IP: {relay_ip}", hint="Enter a valid IPv4 address", hint_type="user")

    registry = ServerRegistry(SERVERS_FILE)

    # Find exit server
    if exit_arg:
        resolved_exit = _resolve_exit(registry, exit_arg, user)
    else:
        result = _find_exit_for_relay(relay_ip)
        if result is None:
            fail(
                f"Relay {relay_ip} not found",
                hint="Specify exit with --exit, or check: meridian relay list",
                hint_type="user",
            )
        registry, resolved_exit = result

    exit_creds = ServerCredentials.load(resolved_exit.creds_dir / "proxy.yml")

    relay_entry = next((r for r in exit_creds.relays if r.ip == relay_ip), None)
    if relay_entry is None:
        fail(f"Relay {relay_ip} not attached to exit {resolved_exit.ip}", hint_type="user")

    relay_label = relay_entry.name or relay_ip
    info(f"Checking relay: {relay_label} -> exit: {resolved_exit.ip}")
    err_console.print()

    all_ok = True

    # 1. SSH connectivity to relay
    try:
        relay_conn = ServerConnection(ip=relay_ip, user=user or "root")
        relay_conn.check_ssh()
        ok("SSH to relay: connected")
    except Exception:
        err_console.print("  [red bold]\u2717[/red bold] SSH to relay: failed")
        err_console.print(f"    [dim]Cannot connect to {relay_ip} via SSH[/dim]")
        err_console.print()
        warn("Cannot proceed without SSH — check SSH key and user")
        err_console.print()
        return

    # 2. Realm service status
    status = relay_conn.run(f"systemctl is-active {RELAY_SERVICE_NAME}", timeout=10)
    if status.returncode == 0 and status.stdout.strip() == "active":
        ok("Realm service: active")
    else:
        err_console.print(f"  [red bold]\u2717[/red bold] Realm service: {status.stdout.strip() or 'not found'}")
        all_ok = False

    # 3. Relay -> exit TCP connectivity
    import shlex as _shlex

    q_exit = _shlex.quote(resolved_exit.ip)
    tcp_test = relay_conn.run(
        f"bash -c 'echo > /dev/tcp/{q_exit}/443' 2>/dev/null",
        timeout=10,
    )
    if tcp_test.returncode == 0:
        ok(f"Relay -> exit TCP: reachable ({resolved_exit.ip}:443)")
    else:
        err_console.print("  [red bold]\u2717[/red bold] Relay -> exit TCP: unreachable")
        all_ok = False

    # 4. Local -> relay TCP connectivity (port 443)
    from meridian.ssh import tcp_connect

    if tcp_connect(relay_ip, relay_entry.port):
        ok(f"Local -> relay TCP: reachable ({relay_ip}:{relay_entry.port})")
    else:
        err_console.print("  [red bold]\u2717[/red bold] Local -> relay TCP: unreachable")
        all_ok = False

    err_console.print()
    if all_ok:
        ok("All checks passed")
    else:
        warn("Some checks failed — see details above")
    err_console.print()
