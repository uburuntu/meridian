"""Reachability test — check proxy accessibility from the client device (no SSH)."""

from __future__ import annotations

import subprocess
import time

from meridian.commands.resolve import resolve_server
from meridian.config import SERVERS_FILE
from meridian.console import err_console, info, ok, warn
from meridian.credentials import ServerCredentials
from meridian.servers import ServerRegistry


def run(
    ip: str = "",
    domain: str = "",
    sni: str = "",
    requested_server: str = "",
) -> None:
    """Test proxy reachability from the current device. No SSH required."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, explicit_ip=ip)

    # Load saved credentials for domain/SNI if not provided
    proxy_file = resolved.creds_dir / "proxy.yml"
    if proxy_file.exists():
        creds = ServerCredentials.load(proxy_file)
        if not domain:
            domain = creds.domain
        if not sni:
            sni = creds.reality_sni

    sni_host = sni or "www.microsoft.com"
    issues = 0
    checks = 0

    err_console.print("  [bold]Ping[/bold]")
    err_console.print("  [dim]Testing proxy reachability from this device[/dim]")
    err_console.print()

    # 0. Clock check (Reality requires client clock accurate within 30s)
    info("Checking device clock...")
    checks += 1
    try:
        ref_result = subprocess.run(
            ["curl", "-sI", "--max-time", "5", "https://www.google.com/"],
            capture_output=True,
            text=True,
            timeout=8,
            stdin=subprocess.DEVNULL,
        )
        date_header = ""
        for h_line in ref_result.stdout.splitlines():
            if h_line.lower().startswith("date:"):
                date_header = h_line.split(":", 1)[1].strip()
                break

        client_epoch = int(time.time())
        if date_header:
            ref_epoch = _parse_http_date(date_header)
            if ref_epoch:
                clock_drift = abs(client_epoch - ref_epoch)
                if clock_drift > 30:
                    warn(f"Device clock is off by {clock_drift}s (Reality needs <30s)")
                    err_console.print("       Enable automatic date/time in your device settings.")
                    issues += 1
                else:
                    ok("Device clock OK")
            else:
                ok("Clock check skipped (date parsing unavailable)")
        else:
            ok("Clock check skipped (offline)")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        ok("Clock check skipped (offline)")

    # 1. TCP connect to port 443
    info(f"Connecting to {resolved.ip}:443...")
    checks += 1
    if _tcp_connect(resolved.ip, 443, timeout=5):
        ok("Port 443 is reachable")
    else:
        warn("Port 443 is not reachable")
        err_console.print("       Possible causes:")
        err_console.print("       - Cloud firewall / security group blocks port 443")
        err_console.print("       - Your ISP or network blocks this server's IP")
        err_console.print("       - Server is down or proxy is not running")
        issues += 1

    # 2. TLS handshake -- Reality should present the SNI target's certificate
    info(f"Checking TLS handshake (Reality -> {sni_host})...")
    checks += 1
    try:
        tls_result = subprocess.run(
            ["bash", "-c", f"echo | openssl s_client -connect {resolved.ip}:443 -servername {sni_host} 2>/dev/null"],
            capture_output=True,
            text=True,
            timeout=8,
            stdin=subprocess.DEVNULL,
        )
        tls_output = tls_result.stdout
        if "CONNECTED" in tls_output and "Certificate chain" in tls_output:
            # Extract CN
            cert_cn = ""
            for tls_line in tls_output.splitlines():
                if "subject=" in tls_line:
                    parts = tls_line.split("CN = ")
                    if len(parts) > 1:
                        cert_cn = parts[1].strip()
                    break
            suffix = f" (cert: {cert_cn})" if cert_cn else ""
            ok(f"TLS handshake OK{suffix}")
        elif "CONNECTED" in tls_output:
            ok("TLS handshake OK")
        else:
            warn("TLS handshake failed")
            err_console.print("       Reality proxy may not be running, or connection is blocked.")
            issues += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        warn("TLS handshake failed (timeout or openssl not found)")
        issues += 1

    # 3. If domain mode, check HTTPS
    if domain:
        info(f"Checking domain https://{domain}/ ...")
        checks += 1
        try:
            http_result = subprocess.run(
                [
                    "curl",
                    "-sSf",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "--connect-timeout",
                    "5",
                    "--max-time",
                    "10",
                    f"https://{domain}/",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                stdin=subprocess.DEVNULL,
            )
            http_code = http_result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            http_code = "000"

        if http_code and http_code[0] in ("2", "3"):
            ok(f"Domain is responding (HTTP {http_code})")
        elif http_code == "000":
            warn("Domain is not reachable")
            err_console.print("       Check DNS settings and that Caddy is running on the server.")
            issues += 1
        else:
            warn(f"Domain returned HTTP {http_code}")
            issues += 1

    # Summary
    err_console.print()
    if issues == 0:
        err_console.print(f"  [ok]All {checks} checks passed.[/ok] Server is reachable from this device.")
        err_console.print("  [dim]If your VPN client can't connect, the issue is likely:[/dim]")
        err_console.print("  [dim]  - Incorrect connection link (re-scan the QR code)[/dim]")
        err_console.print("  [dim]  - VPN app misconfiguration (try v2rayNG or Hiddify)[/dim]")
    else:
        err_console.print(
            f"  [error]{issues} issue(s) found.[/error] The server is not fully reachable from this device."
        )
        err_console.print("  [dim]This means the problem is between your device and the server,[/dim]")
        err_console.print("  [dim]not with the Meridian deployment itself.[/dim]")
        err_console.print()
        err_console.print("  [dim]Common fixes:[/dim]")
        err_console.print("  [dim]  - Open port 443/TCP in your cloud provider's firewall[/dim]")
        err_console.print("  [dim]  - Try from a different network (mobile data, another Wi-Fi)[/dim]")
        err_console.print("  [dim]  - Your ISP may be blocking this server's IP -- try a different server[/dim]")
    err_console.print()


def _tcp_connect(host: str, port: int, timeout: int = 5) -> bool:
    """Test TCP connectivity via bash /dev/tcp."""
    try:
        result = subprocess.run(
            ["bash", "-c", f"echo >/dev/tcp/{host}/{port}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _parse_http_date(date_str: str) -> int | None:
    """Parse an HTTP Date header into epoch seconds."""
    import calendar
    import email.utils

    try:
        parsed = email.utils.parsedate(date_str)
        if parsed:
            return int(calendar.timegm(parsed))
    except Exception:
        pass
    return None
