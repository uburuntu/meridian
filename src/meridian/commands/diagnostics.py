"""System diagnostics collection for bug reports."""

from __future__ import annotations

import platform
import re
import shlex
import shutil

from meridian.commands.resolve import (
    ensure_server_connection,
    fetch_credentials,
    resolve_server,
)
from meridian.config import SERVERS_FILE
from meridian.console import err_console, line
from meridian.credentials import ServerCredentials
from meridian.servers import ServerRegistry


def run(
    ip: str = "",
    sni: str = "",
    user: str = "root",
    ai: bool = False,
    requested_server: str = "",
) -> None:
    """Collect system info from the server for bug reports. Redacts secrets."""
    registry = ServerRegistry(SERVERS_FILE)
    resolved = resolve_server(registry, requested_server=requested_server, explicit_ip=ip, user=user)

    ensure_server_connection(resolved)
    fetch_credentials(resolved)

    from meridian import __version__

    err_console.print()
    err_console.print("  [bold]Meridian Diagnostics[/bold]")
    err_console.print("  [dim]Collecting system info for bug reports...[/dim]")
    err_console.print("  [warn]Note: secrets (passwords, UUIDs, keys) are redacted.[/warn]")
    err_console.print()

    sections: list[tuple[str, str]] = []

    # --- Local Machine ---
    local_os = platform.platform()
    ansible_ver = "not installed"
    if shutil.which("ansible"):
        import subprocess

        try:
            r = subprocess.run(
                ["ansible", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                ansible_ver = r.stdout.splitlines()[0] if r.stdout else "unknown"
        except Exception:
            pass

    sections.append(
        (
            "Local Machine",
            f"OS: {local_os}\nAnsible: {ansible_ver}\nMeridian: {__version__}",
        )
    )

    # --- Server info ---
    os_info = (
        resolved.conn.run("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME", timeout=10).stdout.strip() or "unknown"
    )
    kernel = resolved.conn.run("uname -r", timeout=10).stdout.strip() or "unknown"
    uptime = resolved.conn.run("uptime", timeout=10).stdout.strip() or "unknown"
    disk = resolved.conn.run("df -h / 2>/dev/null | tail -1", timeout=10).stdout.strip() or "unknown"
    memory = resolved.conn.run("free -h 2>/dev/null | grep Mem", timeout=10).stdout.strip() or "unknown"

    sections.append(
        (
            "Server",
            f"{os_info}\nKernel: {kernel}\n{uptime}\nDisk: {disk}\nMemory: {memory}",
        )
    )

    # --- Docker ---
    docker_ver = resolved.conn.run("docker --version 2>&1", timeout=10).stdout.strip() or "not installed"
    docker_ps = (
        resolved.conn.run(
            "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>&1",
            timeout=10,
        ).stdout.strip()
        or "no containers"
    )

    sections.append(("Docker", f"{docker_ver}\n{docker_ps}"))

    # --- 3x-ui Logs (redacted) ---
    xray_logs = (
        resolved.conn.run(
            "docker logs 3x-ui --tail 50 2>&1 | grep -v '^\\s*$' | sort -u | tail -20",
            timeout=15,
        ).stdout.strip()
        or "container not running"
    )
    xray_logs = _redact_secrets(xray_logs)

    sections.append(("3x-ui Logs", xray_logs))

    # --- Listening Ports ---
    ports = (
        resolved.conn.run(
            "ss -tlnp sport = :443 or sport = :80 or sport = :8443 or sport = :8444 2>&1",
            timeout=10,
        ).stdout.strip()
        or "unknown"
    )

    sections.append(("Listening Ports", ports))

    # --- Firewall ---
    ufw = resolved.conn.run("ufw status verbose 2>&1", timeout=10).stdout.strip() or "ufw not available"

    sections.append(("Firewall (UFW)", ufw))

    # --- SNI Target ---
    sni_host = sni or "www.microsoft.com"
    q_sni = shlex.quote(sni_host)
    sni_check = (
        resolved.conn.run(
            f"echo | openssl s_client -connect {q_sni}:443 -servername {q_sni} 2>/dev/null "
            f"| grep -E 'subject=|issuer=|CONNECTED'",
            timeout=10,
        ).stdout.strip()
        or "unreachable"
    )

    sections.append((f"SNI Target ({sni_host})", sni_check))

    # --- Domain DNS ---
    proxy_file = resolved.creds_dir / "proxy.yml"
    if proxy_file.exists():
        creds = ServerCredentials.load(proxy_file)
        if creds.domain:
            q_domain = shlex.quote(creds.domain)
            dns_result = (
                resolved.conn.run(f"dig +short {q_domain} @8.8.8.8 2>/dev/null", timeout=10).stdout.strip()
                or "dig not available"
            )
            sections.append((f"Domain DNS ({creds.domain})", dns_result))

    # --- Output ---
    err_console.print()
    line()
    err_console.print()
    err_console.print("  [bold]Diagnostics collected.[/bold]\n")

    diag_text = _format_sections(sections)

    if ai:
        from meridian.ai import build_ai_prompt

        build_ai_prompt("diagnostics", diag_text, __version__)
    else:
        err_console.print("  1. Review the output below for any private info you want to remove")
        err_console.print("  2. Copy the markdown block into a new issue:")
        err_console.print("     [info]https://github.com/uburuntu/meridian/issues/new[/info]")
        err_console.print()
        line()
        err_console.print()
        err_console.print(diag_text)
        err_console.print()
        line()
        err_console.print()
        err_console.print("  [dim]Secrets (UUIDs, passwords, keys) are auto-redacted.[/dim]\n")
        err_console.print("  [dim]Or get AI help: meridian diagnostics --ai[/dim]\n")


def _redact_secrets(text: str) -> str:
    """Redact UUIDs, passwords, and keys from text."""
    # Redact UUIDs
    text = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "[UUID-REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # Redact passwords/keys/secrets
    text = re.sub(
        r"([Pp]assword|[Kk]ey|[Ss]ecret)[=: ]*[^ ]*",
        r"\1=[REDACTED]",
        text,
    )
    return text


def _format_sections(sections: list[tuple[str, str]]) -> str:
    """Format diagnostic sections as markdown."""
    parts: list[str] = []
    for title, body in sections:
        parts.append(f"### {title}\n```\n{body}\n```")
    return "\n\n".join(parts)
