"""SNI scanner — find optimal Reality SNI targets on the server's network."""

from __future__ import annotations

import shlex

from meridian.commands.resolve import (
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import SERVERS_FILE
from meridian.console import err_console, fail, info, line, ok, prompt, warn
from meridian.credentials import ServerCredentials
from meridian.servers import ServerRegistry


def run(
    ip: str = "",
    user: str = "root",
    requested_server: str = "",
) -> None:
    """Download RealiTLScanner, scan the server's subnet, and let user pick an SNI target."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, explicit_ip=ip, user=user)

    resolved = ensure_server_connection(resolved)
    fetch_credentials(resolved)

    err_console.print()
    err_console.print("  [bold]SNI Scanner[/bold]")
    err_console.print("  [dim]Finding optimal Reality SNI targets near your server...[/dim]")
    err_console.print()

    # Detect server architecture
    arch_result = resolved.conn.run("uname -m", timeout=10)
    raw_arch = arch_result.stdout.strip()
    match raw_arch:
        case "x86_64":
            arch = "64"
        case "aarch64":
            warn("RealiTLScanner has no arm64 build. You can set SNI manually with --sni.")
            return
        case _:
            fail(f"Unsupported architecture: {raw_arch}", hint_type="system")

    # Download RealiTLScanner to server
    scanner_url = f"https://github.com/XTLS/RealiTLScanner/releases/latest/download/RealiTLScanner-linux-{arch}"
    q_url = shlex.quote(scanner_url)
    info("Downloading RealiTLScanner...")
    dl_result = resolved.conn.run(
        f"curl -sSfL --max-time 30 -o /tmp/realitlscanner {q_url} </dev/null && chmod +x /tmp/realitlscanner",
        timeout=40,
    )
    if dl_result.returncode != 0:
        fail("Failed to download RealiTLScanner. Check network connectivity.", hint_type="system")

    # Get server's subnet CIDR for scanning
    cidr_result = resolved.conn.run(
        "ip addr show | grep 'inet ' | grep -v '127.0.0\\|172.17\\|10.0\\|192.168' | head -1 | awk '{print $2}'",
        timeout=10,
    )
    server_cidr = cidr_result.stdout.strip()
    if not server_cidr:
        server_cidr = f"{resolved.ip}/24"

    # Run scan
    q_cidr = shlex.quote(server_cidr)
    info(f"Scanning {server_cidr} for TLS targets (this takes 30-60 seconds)...")
    resolved.conn.run(
        f"cd /tmp && timeout 90 ./realitlscanner -addr {q_cidr}"
        " -out /tmp/meridian-scan.csv -thread 4 -timeout 5 >/dev/null 2>&1",
        timeout=100,
    )

    # Clean up binary, read CSV, clean up CSV — all in one SSH call
    csv_result = resolved.conn.run(
        "cat /tmp/meridian-scan.csv 2>/dev/null; rm -f /tmp/realitlscanner /tmp/meridian-scan.csv",
        timeout=10,
    )
    csv_output = csv_result.stdout.strip()

    if not csv_output or csv_output == "IP,ORIGIN,CERT_DOMAIN,CERT_ISSUER,GEO_CODE":
        warn("Scan produced no results. The server may have limited network visibility.")
        err_console.print(f"\n  [dim]You can manually set SNI with: meridian setup {resolved.ip} --sni DOMAIN[/dim]\n")
        return

    # Parse CSV: extract cert_domain (column 3), skip header, deduplicate, filter bad targets
    domains: list[str] = []
    for csv_line in csv_output.splitlines():
        parts = csv_line.split(",")
        if len(parts) < 3:
            continue
        csv_ip, _origin, cert_domain = parts[0], parts[1], parts[2]
        if csv_ip == "IP":
            continue  # header
        if not cert_domain:
            continue
        if cert_domain.startswith("*"):
            continue  # wildcard certs
        # Filter known-bad targets
        if any(bad in cert_domain for bad in ("apple.com", "icloud.com")):
            continue
        # Skip the server's own IP in domain
        if resolved.ip in cert_domain:
            continue
        # Deduplicate
        if cert_domain not in domains:
            domains.append(cert_domain)

    if not domains:
        warn("No suitable SNI targets found.")
        err_console.print(f"\n  [dim]You can manually set SNI with: meridian setup {resolved.ip} --sni DOMAIN[/dim]\n")
        return

    err_console.print()
    line()
    err_console.print()
    err_console.print(f"  [bold]Found {len(domains)} SNI targets:[/bold]\n")

    for i, domain in enumerate(domains, 1):
        err_console.print(f"    [info]{i}[/info]) {domain}")

    err_console.print()
    choice = prompt(f"Select a target (1-{len(domains)}) or press Enter to skip")

    if choice and choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(domains):
            selected = domains[idx - 1]

            # Save to credentials
            resolved.creds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            proxy_file = resolved.creds_dir / "proxy.yml"
            creds = ServerCredentials.load(proxy_file)
            creds.server.scanned_sni = selected
            creds.save(proxy_file)

            err_console.print()
            ok(f"Saved: {selected}")
            err_console.print(f"  [dim]Use it: meridian setup {resolved.ip} --sni {selected}[/dim]")
            err_console.print("  [dim]Or it will be suggested automatically during setup.[/dim]")
            err_console.print("  [dim]Tip: with --domain, your own domain works as SNI too (self-steal).[/dim]\n")
            return

    info("Skipped. You can set SNI manually with --sni flag.")
    err_console.print()
