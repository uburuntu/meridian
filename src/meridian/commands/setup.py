"""Deploy proxy server — interactive wizard and playbook execution."""

from __future__ import annotations

import subprocess

from meridian.ansible import ensure_ansible, ensure_collections, ensure_qrencode, get_playbooks_dir, run_playbook
from meridian.commands.resolve import (
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import CREDS_BASE, SERVERS_FILE, is_ipv4
from meridian.console import confirm, err_console, fail, info, line, prompt
from meridian.credentials import ServerCredentials
from meridian.servers import ServerEntry, ServerRegistry


def run(
    ip: str = "",
    domain: str = "",
    email: str = "",
    sni: str = "",
    xhttp: bool = False,
    name: str = "",
    user: str = "root",
    yes: bool = False,
) -> None:
    """Deploy a VLESS+Reality proxy server."""
    registry = ServerRegistry(SERVERS_FILE)
    server_ip = ip
    ansible_user = user

    # Interactive wizard if no IP given
    if not server_ip:
        sni_display = sni or "www.microsoft.com"
        err_console.print("  Deploy a VLESS+Reality proxy server.")
        err_console.print("  Invisible to DPI, active probing, and TLS fingerprinting.")
        err_console.print(f"  Your server will impersonate [dim]{sni_display}[/dim] -- probes")
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

        ansible_user = prompt("SSH user", default="root")
        if ansible_user != "root":
            err_console.print("  [dim](sudo will be used for privileged operations)[/dim]")

        err_console.print()
        err_console.print("  [bold]Optional -- CDN fallback:[/bold]\n")

        # Suggest domain from saved credentials
        suggested_domain = ""
        creds_dir = CREDS_BASE / server_ip
        if (creds_dir / "proxy.yml").exists():
            saved_creds = ServerCredentials.load(creds_dir / "proxy.yml")
            suggested_domain = saved_creds.domain

        if suggested_domain:
            err_console.print(f"  [dim]Detected: {suggested_domain}[/dim]")

        domain = prompt("Domain", default=suggested_domain or "skip")
        if domain in ("skip", ""):
            domain = ""

        err_console.print()
        line()
        err_console.print()
        err_console.print("  [bold]Summary[/bold]\n")
        err_console.print(f"  Target:  [ok]{ansible_user}@{server_ip}[/ok]")
        if domain:
            err_console.print(f"  Domain:  [ok]{domain}[/ok]")
            err_console.print("  Mode:    Reality + CDN fallback")
        else:
            err_console.print("  Domain:  [dim](none)[/dim]")
            err_console.print("  Mode:    Standalone (Reality only)")
        err_console.print()
        line()

        if not yes:
            confirm(f"Deploy to {ansible_user}@{server_ip}?")
        err_console.print()

    # Validate IP
    if not is_ipv4(server_ip):
        fail(f"Invalid IP address: {server_ip}")

    # Resolve and prepare
    resolved = resolve_server(
        registry,
        explicit_ip=server_ip,
        user=ansible_user,
    )

    ensure_ansible()
    ensure_qrencode()
    playbooks_dir = get_playbooks_dir()
    ensure_collections(playbooks_dir)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    # Suggest scanned SNI if available and no --sni was given
    if not sni:
        proxy_file = resolved.creds_dir / "proxy.yml"
        if proxy_file.exists():
            creds = ServerCredentials.load(proxy_file)
            if creds.scanned_sni:
                info(f"Detected optimal SNI from scan: {creds.scanned_sni}")
                if yes:
                    sni = creds.scanned_sni
                else:
                    answer = prompt(f"Use {creds.scanned_sni} as SNI target? (Y/n)")
                    if answer.lower() != "n":
                        sni = creds.scanned_sni

    # Build extra vars
    extra_vars: dict[str, str] = {}
    if domain:
        extra_vars["domain"] = domain
    if email:
        extra_vars["email"] = email
    if sni:
        extra_vars["reality_sni"] = sni
    if name:
        extra_vars["first_client_name"] = name
    if xhttp:
        extra_vars["xhttp_enabled"] = "true"

    err_console.print()
    info(f"Configuring server at {resolved.ip}...")
    if domain:
        info(f"Domain: {domain}")
    if xhttp:
        info("XHTTP: enabled (enhanced stealth)")
    err_console.print()

    rc = run_playbook(
        "playbook.yml",
        ip=resolved.ip,
        creds_dir=resolved.creds_dir,
        extra_vars=extra_vars,
        local_mode=resolved.local_mode,
        user=resolved.user,
    )
    if rc != 0:
        fail("Setup playbook failed")

    # Register server
    registry.add(ServerEntry(host=resolved.ip, user=resolved.user))

    # Success output
    client_label = name or "default"
    html_files = list(resolved.creds_dir.glob(f"*-{client_label}-connection-info.html"))
    txt_files = list(resolved.creds_dir.glob("*-connection-info.txt"))

    err_console.print("\n  [ok][bold]Done![/bold][/ok]\n")
    err_console.print("  [bold]Next steps:[/bold]\n")

    if html_files:
        err_console.print("  [ok]1.[/ok] Send this file to whoever needs access:")
        err_console.print(f"     [bold]{html_files[0]}[/bold]")
        err_console.print("     [dim](They open it, scan the QR code, and connect)[/dim]\n")

    if txt_files:
        err_console.print("  [ok]2.[/ok] View connection details:")
        err_console.print(f"     [info]cat {txt_files[0]}[/info]\n")

    err_console.print("  [ok]3.[/ok] Test that the proxy works:")
    err_console.print(f"     [info]meridian ping {resolved.ip}[/info]")
    ping_url = f"https://meridian.msu.rocks/ping?ip={resolved.ip}"
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
