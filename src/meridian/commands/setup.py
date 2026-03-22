"""Deploy proxy server — interactive wizard and provisioner execution."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from meridian.commands.resolve import (
    ResolvedServer,
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import CREDS_BASE, DEFAULT_PANEL_PORT, DEFAULT_SNI, SERVERS_FILE, is_ipv4
from meridian.console import confirm, err_console, fail, info, line, ok, prompt, warn
from meridian.credentials import ServerCredentials
from meridian.servers import ServerEntry, ServerRegistry


def run(
    ip: str = "",
    domain: str = "",
    email: str = "",
    sni: str = "",
    xhttp: bool = True,
    name: str = "",
    user: str = "root",
    yes: bool = False,
    requested_server: str = "",
) -> None:
    """Deploy a VLESS+Reality proxy server."""
    registry = ServerRegistry(SERVERS_FILE)
    server_ip = ip
    ssh_user = user

    # --server flag: resolve from registry
    if requested_server:
        if server_ip:
            fail(
                "Use either the IP address or --server, not both.\n"
                "  Example: meridian deploy 1.2.3.4  OR  meridian deploy --server mybox",
                hint_type="user",
            )
        entry = registry.find(requested_server)
        if not entry:
            if is_ipv4(requested_server):
                server_ip = requested_server
            else:
                fail(
                    f"Server '{requested_server}' not found",
                    hint="See registered servers: meridian server list",
                    hint_type="user",
                )
        else:
            server_ip = entry.host
            if user == "root" and entry.user:
                ssh_user = entry.user

    # Interactive wizard if no IP given
    if not server_ip:
        server_ip, ssh_user, sni, domain, email, xhttp = _interactive_wizard(
            sni=sni,
            xhttp=xhttp,
            domain=domain,
            email=email,
            yes=yes,
        )

    # Validate IP
    if not is_ipv4(server_ip):
        fail(
            f"Invalid IP address: {server_ip}",
            hint="Enter a valid IPv4 address (e.g. meridian deploy 123.45.67.89)",
            hint_type="user",
        )

    # Resolve and prepare
    resolved = resolve_server(
        registry,
        explicit_ip=server_ip,
        user=ssh_user,
    )

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    # Migrate v1 credentials to v2
    proxy_file = resolved.creds_dir / "proxy.yml"
    if proxy_file.exists():
        creds = ServerCredentials.load(proxy_file)
        if creds.has_credentials:
            creds.save(proxy_file)  # Re-save as v2 if loaded from v1

    # Suggest scanned SNI if available and no --sni was given
    if not sni:
        proxy_file = resolved.creds_dir / "proxy.yml"
        if proxy_file.exists():
            creds = ServerCredentials.load(proxy_file)
            if creds.server.scanned_sni:
                info(f"Detected optimal SNI from scan: {creds.server.scanned_sni}")
                if yes:
                    sni = creds.server.scanned_sni
                else:
                    answer = prompt(f"Use {creds.server.scanned_sni} as SNI target? (Y/n)")
                    if answer.lower() != "n":
                        sni = creds.server.scanned_sni

    # Route to legacy Ansible or new Python provisioner
    if name and not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
        fail(
            f"Client name '{name}' is invalid",
            hint="Use letters, numbers, hyphens, and underscores.",
            hint_type="user",
        )
    _run_provisioner(resolved, domain, sni, name, xhttp)

    # Register server
    registry.add(ServerEntry(host=resolved.ip, user=resolved.user))

    # Success output
    _print_success(resolved, name, domain)


def _interactive_wizard(
    sni: str,
    xhttp: bool,
    domain: str,
    email: str,
    yes: bool,
) -> tuple[str, str, str, str, str, bool]:
    """Interactive deployment wizard. Returns (ip, user, sni, domain, email, xhttp)."""
    from meridian.ssh import ServerConnection

    # --- Protocol explanation ---
    err_console.print()
    info("Protocol: VLESS + Reality")
    err_console.print("  [dim]Your server impersonates a real website \u2014 censors see[/dim]")
    err_console.print("  [dim]normal HTTPS traffic, not a VPN connection.[/dim]")
    err_console.print()

    # --- Server IP ---
    detected_ip = _detect_public_ip()

    while True:
        server_ip = prompt("Server IP address", default=detected_ip)
        if is_ipv4(server_ip):
            break
        err_console.print("  [error]Enter a valid IPv4 address (e.g. 123.45.67.89)[/error]")

    # --- SSH user ---
    ssh_user = prompt("SSH user", default="root")
    if ssh_user != "root":
        err_console.print("  [dim](sudo will be used for privileged operations)[/dim]")

    # --- Offer scan for SNI ---
    if not sni:
        err_console.print()
        err_console.print("  [bold]Camouflage target[/bold]")
        err_console.print("  [dim]Your server pretends to be a real website. Targets on the[/dim]")
        err_console.print("  [dim]same network are hardest for censors to distinguish.[/dim]")
        err_console.print()

        # Check for previously scanned SNI
        saved_scanned_sni = ""
        creds_dir = CREDS_BASE / server_ip
        if (creds_dir / "proxy.yml").exists():
            saved_creds = ServerCredentials.load(creds_dir / "proxy.yml")
            saved_scanned_sni = saved_creds.server.scanned_sni or ""

        if saved_scanned_sni:
            info(f"Previous scan found: {saved_scanned_sni}")
            if not yes:
                answer = prompt(f"Use {saved_scanned_sni}? (Y/n)")
                if answer.lower() != "n":
                    sni = saved_scanned_sni
            else:
                sni = saved_scanned_sni

        if not sni and not yes:
            if _confirm_scan():
                # Establish SSH for scan
                try:
                    conn = ServerConnection(ip=server_ip, user=ssh_user)
                    conn.check_ssh()

                    from meridian.commands.scan import scan_for_sni

                    candidates = scan_for_sni(conn, server_ip)

                    if candidates:
                        err_console.print()
                        top = candidates[:5]
                        for i, candidate in enumerate(top, 1):
                            marker = " [dim]\u2190 recommended[/dim]" if i == 1 else ""
                            err_console.print(f"    {i}. {candidate}{marker}")
                        skip_idx = len(top) + 1
                        err_console.print(f"    {skip_idx}. [dim]Skip \u2014 use default ({DEFAULT_SNI})[/dim]")
                        err_console.print()

                        choice = prompt("Choose", default="1")
                        if choice.isdigit():
                            idx = int(choice) - 1
                            if 0 <= idx < len(top):
                                sni = top[idx]

                                # Save scanned SNI to credentials
                                creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                                proxy_file = creds_dir / "proxy.yml"
                                creds = ServerCredentials.load(proxy_file)
                                creds.server.scanned_sni = sni
                                creds.save(proxy_file)
                    else:
                        warn("No targets found on the same network")
                except Exception:
                    warn("Could not connect to scan. You can run 'meridian scan' later.")

        if not sni:
            sni = DEFAULT_SNI

    # --- Domain (optional) ---
    err_console.print()
    err_console.print("  [bold]CDN fallback[/bold] [dim](optional)[/dim]")
    err_console.print("  [dim]Routes through Cloudflare when direct connection is blocked.[/dim]")
    err_console.print("  [dim]Guide: getmeridian.org/docs/en/domain-mode/[/dim]")

    # Suggest domain from saved credentials
    suggested_domain = domain
    if not suggested_domain:
        creds_dir = CREDS_BASE / server_ip
        if (creds_dir / "proxy.yml").exists():
            saved_creds = ServerCredentials.load(creds_dir / "proxy.yml")
            suggested_domain = saved_creds.server.domain or ""

    if suggested_domain:
        err_console.print(f"  [dim]Detected: {suggested_domain}[/dim]")

    if not yes:
        domain_input = prompt("Domain (leave blank to skip)", default=suggested_domain or "")
        if domain_input and domain_input != "skip":
            domain = domain_input
        elif not domain_input or domain_input == "skip":
            domain = ""
    elif not domain:
        domain = ""

    # --- Summary panel ---
    from rich.panel import Panel

    protocol_line = "VLESS + Reality (TCP)"
    if xhttp:
        protocol_line += "\n           + XHTTP fallback (same port)"
    if domain:
        protocol_line += f"\n           + CDN fallback ({domain})"

    summary = (
        f"Server:     {ssh_user}@{server_ip}\n"
        f"Protocol:   {protocol_line}\n"
        f"Camouflage: {sni}\n"
        f"Mode:       {'CDN fallback' if domain else 'Standalone (IP certificate)'}"
    )

    err_console.print()
    err_console.print(Panel(summary, title="[bold]Deployment plan[/bold]", border_style="cyan", padding=(0, 2)))
    err_console.print()

    # --- Confirm ---
    if not yes:
        confirm(f"Deploy to {ssh_user}@{server_ip}?")
    err_console.print()

    return server_ip, ssh_user, sni, domain, email, xhttp


def _confirm_scan() -> bool:
    """Ask user if they want to scan. Returns True/False without exiting on 'n'."""
    try:
        with open("/dev/tty") as tty:
            err_console.print("  [info]\u2192[/info] Scan for optimal target? (~30 seconds) [dim][Y/n][/dim] ", end="")
            answer = tty.readline().strip().lower()
    except OSError:
        return False
    return answer in ("", "y", "yes")


def _run_provisioner(
    resolved: ResolvedServer,
    domain: str,
    sni: str,
    name: str,
    xhttp: bool,
) -> None:
    """Run the Python provisioner pipeline."""
    from meridian.provision import ProvisionContext, Provisioner, build_setup_steps

    ctx = ProvisionContext(
        ip=resolved.ip,
        user=resolved.user,
        domain=domain,
        sni=sni or DEFAULT_SNI,
        xhttp_enabled=xhttp,
        hosted_page=True,  # always serve connection pages on server
        creds_dir=str(resolved.creds_dir),
    )

    # Default panel port — 3x-ui starts on 2053. ConfigurePanel may change it later.
    ctx.panel_port = DEFAULT_PANEL_PORT
    # Deterministic port derivation (hashlib, not hash() which is randomized per process)
    ip_hash = int(hashlib.sha256(ctx.ip.encode()).hexdigest()[:8], 16)
    ctx.xhttp_port = 30000 + (ip_hash % 10000)
    ctx.reality_port = 443 if not ctx.needs_web_server else (10000 + ip_hash % 1000)

    # Load existing credentials into context if available
    proxy_file = Path(ctx.creds_dir) / "proxy.yml"
    if proxy_file.exists():
        from meridian.credentials import ServerCredentials

        creds = ServerCredentials.load(proxy_file)
        ctx["credentials"] = creds
        if creds.panel.username and creds.panel.password:
            ctx["panel_configured"] = True
            ctx["panel_username"] = creds.panel.username
            ctx["panel_password"] = creds.panel.password
            ctx["web_base_path"] = creds.panel.web_base_path or ""
            ctx["info_page_path"] = creds.panel.info_page_path or ""
            # Use saved panel port (not computed) for re-runs
            if creds.panel.port:
                ctx.panel_port = creds.panel.port
            # Load protocol paths so downstream steps (InstallCaddy) have them
            # even when ConfigurePanel is skipped on re-deploy
            if creds.wss.ws_path:
                ctx["ws_path"] = creds.wss.ws_path
            if creds.xhttp.xhttp_path:
                ctx["xhttp_path"] = creds.xhttp.xhttp_path

    # First client name
    ctx["first_client_name"] = name or "default"

    err_console.print()
    info(f"Configuring server at {ctx.ip}...")
    if domain:
        info(f"Domain: {domain}")
    if xhttp:
        info("XHTTP: enabled (enhanced stealth)")
    err_console.print()

    steps = build_setup_steps(ctx)
    provisioner = Provisioner(steps)

    from meridian.ssh import ServerConnection

    conn = resolved.conn
    if not isinstance(conn, ServerConnection):
        fail("No SSH connection available", hint_type="bug")

    results = provisioner.run(conn, ctx)

    # Check for failures
    failed = [r for r in results if r.status == "failed"]
    if failed:
        fail(
            "Setup failed",
            hint=f"Step '{failed[0].name}' failed: {failed[0].detail}\nRun: meridian preflight {ctx.ip}",
            hint_type="system",
        )

    err_console.print()
    ok("All steps completed successfully")


def _print_success(resolved: ResolvedServer, name: str, domain: str) -> None:
    """Print success output after deployment."""
    client_label = name or "default"
    creds_dir = resolved.creds_dir
    html_files = list(creds_dir.glob(f"*-{client_label}-connection-info.html"))
    txt_files = list(creds_dir.glob("*-connection-info.txt"))

    # Check if there's a hosted page URL from credentials
    hosted_page_url = ""
    proxy_file = creds_dir / "proxy.yml"
    if proxy_file.exists():
        creds = ServerCredentials.load(proxy_file)
        if creds.server.hosted_page and creds.panel.info_page_path and creds.reality.uuid:
            ip = creds.server.ip or resolved.ip
            hosted_page_url = f"https://{ip}/{creds.panel.info_page_path}/{creds.reality.uuid}/"

    err_console.print("\n  [ok][bold]Done![/bold][/ok]\n")
    ok("Your proxy server is live and ready to use.")
    err_console.print()
    err_console.print("  [bold]Next steps:[/bold]\n")

    if hosted_page_url:
        err_console.print("  [ok]1.[/ok] Share this link with whoever needs access:")
        err_console.print(f"     [bold]{hosted_page_url}[/bold]")
        err_console.print("     [dim](They open it, scan the QR code, and connect)[/dim]\n")
    elif html_files:
        err_console.print("  [ok]1.[/ok] Send this file to whoever needs access:")
        err_console.print(f"     [bold]{html_files[0]}[/bold]")
        err_console.print("     [dim](They open it, scan the QR code, and connect)[/dim]\n")

    if txt_files:
        err_console.print("  [ok]2.[/ok] View connection details:")
        err_console.print(f"     [info]cat {txt_files[0]}[/info]\n")

    err_console.print("  [ok]3.[/ok] Test that the proxy works:")
    server_ip = resolved.ip
    err_console.print(f"     [info]meridian test {server_ip}[/info]")
    ping_url = f"https://getmeridian.org/ping?ip={server_ip}"
    if domain:
        ping_url += f"&domain={domain}"
    err_console.print(f"     [dim]Or from browser: {ping_url}[/dim]\n")

    err_console.print("  [ok]4.[/ok] Share access with friends:")
    err_console.print("     [info]meridian client add alice[/info]")
    err_console.print("     [info]meridian client list[/info]\n")

    err_console.print()
    line()
    err_console.print("\n  [dim]Feedback & issues: https://github.com/uburuntu/meridian/issues[/dim]\n")


def _detect_public_ip() -> str:
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
