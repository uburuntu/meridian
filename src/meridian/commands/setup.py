"""Deploy proxy server — interactive wizard and provisioner execution."""

from __future__ import annotations

import subprocess
from pathlib import Path

from meridian.commands.resolve import (
    ResolvedServer,
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import CREDS_BASE, DEFAULT_PANEL_PORT, DEFAULT_SNI, SERVERS_FILE, is_ipv4
from meridian.console import confirm, err_console, fail, info, line, ok, prompt
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
        sni_display = sni or DEFAULT_SNI
        err_console.print("  Deploy a private internet connection that censors can't detect.")
        err_console.print(f"  Your server will impersonate [dim]{sni_display}[/dim] — probes")
        err_console.print("  get a real TLS certificate back. Takes ~2 minutes. Safe to re-run.")
        err_console.print()
        line()
        err_console.print()
        err_console.print("  [bold]Where is the server?[/bold]\n")

        detected_ip = _detect_public_ip()

        while True:
            server_ip = prompt("IP address", default=detected_ip)
            if is_ipv4(server_ip):
                break
            err_console.print("  [error]Enter a valid IPv4 address (e.g. 123.45.67.89)[/error]")

        ssh_user = prompt("SSH user", default="root")
        if ssh_user != "root":
            err_console.print("  [dim](sudo will be used for privileged operations)[/dim]")

        err_console.print()
        err_console.print("  [bold]Optional — CDN fallback:[/bold]\n")

        # Suggest domain from saved credentials
        suggested_domain = ""
        creds_dir = CREDS_BASE / server_ip
        if (creds_dir / "proxy.yml").exists():
            saved_creds = ServerCredentials.load(creds_dir / "proxy.yml")
            suggested_domain = saved_creds.server.domain or ""

        if suggested_domain:
            err_console.print(f"  [dim]Detected: {suggested_domain}[/dim]")

        domain = prompt("Domain (optional, leave blank for standalone)", default=suggested_domain or "")
        if domain in ("skip", ""):
            domain = ""

        err_console.print()
        line()
        err_console.print()
        err_console.print("  [bold]Summary[/bold]\n")
        err_console.print(f"  Target:  [ok]{ssh_user}@{server_ip}[/ok]")
        if domain:
            err_console.print(f"  Domain:  [ok]{domain}[/ok]")
            err_console.print("  Mode:    Reality + CDN fallback")
        else:
            err_console.print("  Domain:  [dim](none)[/dim]")
            err_console.print("  Mode:    Standalone (Reality only)")
        sni_display = sni or DEFAULT_SNI
        err_console.print(f"  SNI:     {sni_display}")
        err_console.print(f"  XHTTP:   {'enabled' if xhttp else 'disabled'}")
        err_console.print()
        line()

        if not yes:
            confirm(f"Deploy to {ssh_user}@{server_ip}?")
        err_console.print()

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
    _run_provisioner(resolved, domain, sni, name, xhttp)

    # Register server
    registry.add(ServerEntry(host=resolved.ip, user=resolved.user))

    # Success output
    _print_success(resolved, name, domain)


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
    ctx.xhttp_port = 30000 + (hash(ctx.ip) % 10000)
    ctx.reality_port = 443 if not ctx.needs_web_server else (10000 + hash(ctx.ip) % 1000)

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
    ping_url = f"https://meridian.msu.rocks/ping?ip={server_ip}"
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
