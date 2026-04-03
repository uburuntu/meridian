"""Deploy proxy server — interactive wizard and provisioner execution."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from meridian.commands.resolve import (
    ResolvedServer,
    detect_public_ip,
    ensure_server_connection,
    fetch_credentials,
    is_local_keyword,
    resolve_server,
)
from meridian.config import CREDS_BASE, DEFAULT_PANEL_PORT, DEFAULT_SNI, SERVER_CREDS_DIR, SERVERS_FILE, is_ipv4
from meridian.console import confirm, err_console, fail, info, line, ok, prompt, warn
from meridian.credentials import ServerCredentials
from meridian.servers import ServerEntry, ServerRegistry
from meridian.ssh import ServerConnection


def run(
    ip: str = "",
    domain: str = "",
    email: str = "",
    sni: str = "",
    xhttp: bool = True,
    name: str = "",
    user: str = "root",
    yes: bool = False,
    harden: bool = True,
    requested_server: str = "",
    *,
    server_name: str = "",
    icon: str = "",
    color: str = "",
    decoy: str = "",
) -> None:
    """Deploy a VLESS+Reality proxy server."""
    # --decoy is deprecated (403/404 is now always the default).
    # Accept silently for backwards compatibility but don't use it.

    registry = ServerRegistry(SERVERS_FILE)
    server_ip = ip
    ssh_user = user

    # --server flag: resolve from registry (or 'local' keyword)
    if requested_server:
        if server_ip:
            fail(
                "Use either the IP address or --server, not both.\n"
                "  Example: meridian deploy 1.2.3.4  OR  meridian deploy --server mybox",
                hint_type="user",
            )
        if is_local_keyword(requested_server):
            server_ip = requested_server
        else:
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
        wizard_result = _interactive_wizard(
            sni=sni,
            xhttp=xhttp,
            domain=domain,
            email=email,
            harden=harden,
            yes=yes,
            server_name=server_name,
            icon=icon,
            color=color,
        )
        server_ip, ssh_user, sni, domain, email, xhttp, harden = wizard_result[:7]
        server_name, icon, color = wizard_result[7:]

    # Validate IP (skip for 'local' keyword — resolve_server handles it)
    if not is_local_keyword(server_ip) and not is_ipv4(server_ip):
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
    _check_ports(resolved.conn, resolved.ip, yes)
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

    # Save branding to credentials before provisioning
    if server_name or icon or color:
        from meridian.credentials import BrandingConfig

        proxy_file = resolved.creds_dir / "proxy.yml"
        creds = ServerCredentials.load(proxy_file) if proxy_file.exists() else ServerCredentials()
        if server_name or icon or color:
            creds.branding = BrandingConfig(
                server_name=server_name,
                icon=icon,
                color=color,
            )
        creds.save(proxy_file)

    _run_provisioner(resolved, domain, sni, name, xhttp, harden)

    # Register server
    registry.add(ServerEntry(host=resolved.ip, user=resolved.user))

    # Success output
    _print_success(resolved, name, domain)

    # Offer relay setup
    _offer_relay(resolved, yes)


def _interactive_wizard(
    sni: str,
    xhttp: bool,
    domain: str,
    email: str,
    harden: bool,
    yes: bool,
    server_name: str = "",
    icon: str = "",
    color: str = "",
) -> tuple[str, str, str, str, str, bool, bool, str, str, str]:
    """Interactive deployment wizard.

    Returns (ip, user, sni, domain, email, xhttp, harden,
             server_name, icon, color).
    """
    import os

    # --- Protocol explanation ---
    err_console.print()
    info("Protocol: VLESS + Reality")
    err_console.print("  [dim]Your server impersonates a real website \u2014 censors see[/dim]")
    err_console.print("  [dim]normal HTTPS traffic, not a VPN connection.[/dim]")
    err_console.print()

    # --- Server IP ---
    detected_ip = detect_public_ip()
    is_local = False

    # Offer local deployment if running as root with a public IP
    if detected_ip and os.getuid() == 0:
        info(f"Detected: running as root on this server ({detected_ip})")
        answer = prompt("Deploy locally on this server? [Y/n]")
        if answer.lower() != "n":
            server_ip = "local"
            ssh_user = "root"
            is_local = True
        else:
            is_local = False

    if not is_local:
        while True:
            server_ip = prompt("Server IP address", default=detected_ip)
            if is_ipv4(server_ip) or is_local_keyword(server_ip):
                break
            err_console.print("  [error]Enter a valid IPv4 address (e.g. 123.45.67.89)[/error]")

        if is_local_keyword(server_ip):
            is_local = True
            ssh_user = "root"
        else:
            # --- SSH user ---
            ssh_user = prompt("SSH user", default="root")
            if ssh_user != "root":
                err_console.print("  [dim](sudo will be used for privileged operations)[/dim]")

    # --- Server hardening ---
    if not yes:
        err_console.print()
        err_console.print("  [bold]Server hardening[/bold]")
        err_console.print("  [dim]Disables password SSH login and enables firewall[/dim]")
        err_console.print("  [dim](allows ports 22, 80, 443 only). Skip if you have[/dim]")
        err_console.print("  [dim]other services running on this server.[/dim]")
        err_console.print()
        answer = prompt("Harden server? [Y/n]")
        if answer.lower() == "n":
            harden = False
            warn("Skipping SSH hardening and firewall")
        else:
            harden = True

    # --- Offer scan for SNI ---
    if not sni:
        err_console.print()
        err_console.print("  [bold]Camouflage target[/bold]")
        err_console.print("  [dim]Your server pretends to be a real website. Targets on the[/dim]")
        err_console.print("  [dim]same network are hardest for censors to distinguish.[/dim]")
        err_console.print()

        # Check for previously scanned SNI
        saved_scanned_sni = ""
        if is_local:
            creds_dir = SERVER_CREDS_DIR
        else:
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
                # Establish connection for scan
                try:
                    scan_ip = detected_ip if is_local else server_ip
                    conn = ServerConnection(ip=scan_ip, user=ssh_user, local_mode=is_local)
                    if not is_local:
                        conn.detect_local_mode()
                        if not conn.local_mode:
                            conn.check_ssh()

                    from meridian.commands.scan import scan_for_sni

                    candidates = scan_for_sni(conn, scan_ip)

                    if candidates:
                        err_console.print()
                        top = candidates[:5]
                        for i, candidate in enumerate(top, 1):
                            err_console.print(f"    {i}. {candidate}")
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

    # --- Domain (optional but strongly recommended) ---
    err_console.print()
    err_console.print("  [bold]Domain[/bold] [dim](strongly recommended)[/dim]")
    err_console.print("  [dim]Makes your server indistinguishable from a normal website.[/dim]")
    err_console.print("  [dim]Without a domain, probers see an IP-only certificate —[/dim]")
    err_console.print("  [dim]a valid but less common profile. Also enables CDN fallback.[/dim]")
    err_console.print("  [dim]Guide: getmeridian.org/docs/en/domain-mode/[/dim]")

    # Suggest domain from saved credentials
    suggested_domain = domain
    if not suggested_domain:
        if is_local:
            domain_creds_dir = SERVER_CREDS_DIR
        else:
            domain_creds_dir = CREDS_BASE / server_ip
        if (domain_creds_dir / "proxy.yml").exists():
            saved_creds = ServerCredentials.load(domain_creds_dir / "proxy.yml")
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

    # --- Branding: server name ---
    if not yes and not server_name:
        err_console.print()
        err_console.print("  [bold]Personalize[/bold]")
        err_console.print("  [dim]Make the connection page yours. Your friends see this.[/dim]")
        err_console.print()
        server_name = prompt("Server name", default="My VPN")

    # --- Branding: icon ---
    if not yes and not icon:
        from meridian.branding import ICON_SUGGESTIONS

        err_console.print()
        err_console.print("  [bold]Server icon[/bold]")
        grid = "    "
        for i, emoji in enumerate(ICON_SUGGESTIONS, 1):
            grid += f"{i}. {emoji}  "
        err_console.print(grid)
        err_console.print()
        icon_input = prompt("Pick a number, paste an emoji, or an image URL", default="1")
        if icon_input.isdigit():
            idx = int(icon_input) - 1
            if 0 <= idx < len(ICON_SUGGESTIONS):
                icon = ICON_SUGGESTIONS[idx]
        if not icon:
            from meridian.branding import process_icon

            icon = process_icon(icon_input)
    elif icon:
        # CLI flag provided — process it
        from meridian.branding import process_icon

        processed = process_icon(icon)
        if processed:
            icon = processed

    # --- Branding: color palette ---
    if not yes and not color:
        from meridian.branding import PALETTE_LABELS, PALETTES

        err_console.print()
        err_console.print("  [bold]Color palette[/bold]")
        palette_names = list(PALETTES.keys())
        for i, pname in enumerate(palette_names, 1):
            marker = " [dim]← default[/dim]" if pname == "ocean" else ""
            err_console.print(f"    {i}. {PALETTE_LABELS[pname]}{marker}")
        err_console.print()
        color_input = prompt("Choose", default="1")
        if color_input.isdigit():
            idx = int(color_input) - 1
            if 0 <= idx < len(palette_names):
                color = palette_names[idx]
        if not color:
            # Try matching by name
            from meridian.branding import validate_color

            color = validate_color(color_input) or "ocean"
    elif color:
        from meridian.branding import validate_color

        color = validate_color(color) or "ocean"

    if not color:
        color = "ocean"

    # --- Summary panel ---
    from rich.panel import Panel

    protocol_line = "VLESS + Reality (TCP)"
    if xhttp:
        protocol_line += "\n           + XHTTP fallback (same port)"
    if domain:
        protocol_line += f"\n           + CDN fallback ({domain})"

    icon_display = icon if icon and not icon.startswith("data:") else ""
    branding_line = ""
    if server_name or icon_display or color:
        parts = []
        if icon_display:
            parts.append(icon_display)
        if server_name:
            parts.append(server_name)
        if color:
            parts.append(f"[dim]{color} palette[/dim]")
        branding_line = f"\nBranding:   {' '.join(parts)}"

    server_label = f"this server ({detected_ip}) \u2014 local mode" if is_local else f"{ssh_user}@{server_ip}"
    summary = (
        f"Server:     {server_label}\n"
        f"Protocol:   {protocol_line}\n"
        f"Camouflage: {sni}\n"
        f"Mode:       {'Domain mode (best stealth + CDN fallback)' if domain else 'IP-only (works without a domain)'}"
        f"{branding_line}"
    )

    err_console.print()
    err_console.print(Panel(summary, title="[bold]Deployment plan[/bold]", border_style="cyan", padding=(0, 2)))
    err_console.print()

    # --- Confirm ---
    if not yes:
        if is_local:
            confirm(f"Deploy locally on this server ({detected_ip})?")
        else:
            confirm(f"Deploy to {ssh_user}@{server_ip}?")
    err_console.print()

    return server_ip, ssh_user, sni, domain, email, xhttp, harden, server_name, icon, color


def _confirm_scan() -> bool:
    """Ask user if they want to scan. Returns True/False without exiting on 'n'."""
    try:
        with open("/dev/tty") as tty:
            err_console.print("  [info]\u2192[/info] Scan for optimal target? (~1 minute) [dim][Y/n][/dim] ", end="")
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
    harden: bool = True,
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
        harden=harden,
        creds_dir=str(resolved.creds_dir),
    )

    # Default panel port — 3x-ui starts on 2053. ConfigurePanel may change it later.
    ctx.panel_port = DEFAULT_PANEL_PORT
    # Deterministic port derivation (hashlib, not hash() which is randomized per process)
    ip_hash = int(hashlib.sha256(ctx.ip.encode()).hexdigest()[:8], 16)
    ctx.xhttp_port = 30000 + (ip_hash % 10000)
    ctx.reality_port = 443 if not ctx.needs_web_server else (10000 + ip_hash % 1000)
    ctx.wss_port = 20000 + (ip_hash % 10000)

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
            # Load protocol paths so downstream steps (InstallNginx) have them
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

    err_console.print("  [ok]2.[/ok] View connection details anytime:")
    err_console.print(f"     [info]meridian client show {client_label}[/info]\n")

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

    server_ip = resolved.ip
    err_console.print("  [ok]5.[/ok] Add a relay for resilience (optional):")
    err_console.print(f"     [info]meridian relay deploy RELAY_IP --exit {server_ip}[/info]")
    err_console.print("     [dim]Routes through a domestic IP when the exit gets blocked[/dim]\n")

    err_console.print()
    line()
    err_console.print("\n  [dim]Feedback & issues: https://github.com/uburuntu/meridian/issues[/dim]\n")


def _check_ports(conn: ServerConnection, ip: str, yes: bool) -> None:
    """Check that ports 443 and 80 are available before deploying.

    Allows re-deploy over existing Meridian processes.
    Loops with retry prompt if a non-Meridian process holds a port.
    """
    allowed = {"nginx", "3x-ui", "xray", "haproxy", "caddy"}

    for port in (443, 80):
        while True:
            result = conn.run(f"ss -tlnp sport = :{port} 2>/dev/null | grep LISTEN", timeout=10)
            if not result.stdout.strip():
                break  # port free

            match = re.search(r'users:\(\("([^"]*)"', result.stdout)
            proc = match.group(1) if match else "unknown"
            if proc in allowed:
                break  # Meridian's own process — OK for re-deploy

            warn(f"Port {port} is in use by {proc}")
            err_console.print(f"  [dim]Port {port} must be free for Meridian.[/dim]")
            err_console.print(f"  [dim]Stop {proc} and retry, or press Ctrl+C to abort.[/dim]")
            err_console.print()

            if yes:
                fail(
                    f"Port {port} is occupied by {proc}",
                    hint=f"Stop {proc} first: sudo systemctl stop {proc}",
                    hint_type="user",
                )

            answer = prompt("Retry? [Y/n]")
            if answer.lower() == "n":
                fail("Aborted — port conflict", hint_type="user")


def _offer_relay(resolved: ResolvedServer, yes: bool) -> None:
    """Offer to deploy a relay node after successful exit server deploy."""
    if yes:
        return  # Don't prompt in non-interactive mode

    err_console.print()
    err_console.print("  [bold]Add a relay node?[/bold] [dim](optional)[/dim]")
    err_console.print("  [dim]A relay is a domestic server that forwards traffic to[/dim]")
    err_console.print("  [dim]this exit server. Useful when the IP gets blocked.[/dim]")
    err_console.print()

    answer = prompt("Set up a relay? [y/N]")
    if answer.lower() not in ("y", "yes"):
        err_console.print(f"  [dim]You can add one later: meridian relay deploy RELAY_IP --exit {resolved.ip}[/dim]")
        return

    relay_ip = prompt("Relay server IP")
    if not is_ipv4(relay_ip):
        warn(f"Invalid IP. Set up later: meridian relay deploy RELAY_IP --exit {resolved.ip}")
        return

    relay_name = prompt("Relay name (optional, e.g. ru-moscow)", default="")

    from meridian.commands.relay import run_deploy

    run_deploy(
        relay_ip=relay_ip,
        exit_arg=resolved.ip,
        user="root",
        relay_name=relay_name,
        listen_port=443,
        yes=False,
    )
