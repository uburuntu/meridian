"""Migrate from Meridian 3.x (3x-ui) to 4.0 (Remnawave).

Reads old per-server credentials and prints a migration guide.
Does NOT auto-deploy -- the deployer runs `meridian deploy` manually.
"""

from __future__ import annotations

from pathlib import Path

from meridian.cluster import ClusterConfig
from meridian.config import CLUSTER_CONFIG, CREDS_BASE
from meridian.console import confirm, err_console, fail, info, ok, warn
from meridian.credentials import ServerCredentials


def _find_old_servers(creds_base: Path) -> list[tuple[str, Path]]:
    """Scan credentials dir for proxy.yml files. Returns (dir_name, path) pairs."""
    if not creds_base.is_dir():
        return []
    results = []
    for child in sorted(creds_base.iterdir()):
        proxy = child / "proxy.yml"
        if child.is_dir() and proxy.exists():
            results.append((child.name, proxy))
    return results


def run_migrate() -> None:
    """Scan old 3.x credentials and print a migration guide to 4.0."""

    # 1. Guard: cluster.yml already exists
    if CLUSTER_CONFIG.exists():
        cluster = ClusterConfig.load()
        if cluster.is_configured:
            fail(
                "Cluster already configured (cluster.yml exists)",
                hint="Migration is only needed once. Use 'meridian deploy' to add nodes.",
                hint_type="user",
            )

    # 2. Scan for old servers
    old_servers = _find_old_servers(CREDS_BASE)
    if not old_servers:
        fail(
            f"No 3.x credentials found in {CREDS_BASE}",
            hint="Nothing to migrate. Start fresh with: meridian deploy",
            hint_type="user",
        )

    # 3. Load each server's credentials
    info("Scanning 3.x credentials...")
    err_console.print()

    server_data: list[dict[str, object]] = []
    for dir_name, proxy_path in old_servers:
        creds = ServerCredentials.load(proxy_path)
        ip = creds.server.ip or dir_name
        domain = creds.server.domain or ""
        sni = creds.server.sni or ""
        clients = [c.name for c in creds.clients if c.name]
        relays = [(r.ip, r.name) for r in creds.relays if r.ip]
        branding = creds.branding

        server_data.append(
            {
                "ip": ip,
                "domain": domain,
                "sni": sni,
                "clients": clients,
                "relays": relays,
                "branding_name": branding.server_name,
            }
        )

        # Print summary for this server
        err_console.print(f"  [bold cyan]{ip}[/bold cyan]", end="")
        if domain:
            err_console.print(f"  [dim]domain={domain}[/dim]", end="")
        if sni:
            err_console.print(f"  [dim]sni={sni}[/dim]", end="")
        err_console.print()

        if clients:
            err_console.print(f"    Clients: {', '.join(clients)}")
        if relays:
            relay_labels = [f"{r[0]} ({r[1]})" if r[1] else r[0] for r in relays]
            err_console.print(f"    Relays:  {', '.join(relay_labels)}")
        if branding.server_name:
            err_console.print(f"    Name:    {branding.server_name}")

    total_servers = len(server_data)
    total_clients = sum(len(s["clients"]) for s in server_data)  # type: ignore[arg-type]
    total_relays = sum(len(s["relays"]) for s in server_data)  # type: ignore[arg-type]

    err_console.print()
    err_console.print(
        f"  Found [bold]{total_servers}[/bold] server(s), "
        f"[bold]{total_clients}[/bold] client(s), "
        f"[bold]{total_relays}[/bold] relay(s)"
    )
    err_console.print()

    # 4. Confirm
    confirm("Ready to see migration instructions?")

    # 5. Print migration guide
    err_console.print()
    err_console.print("[bold]Migration guide: 3.x -> 4.0[/bold]")
    err_console.print()
    err_console.print("  Meridian 4.0 replaces 3x-ui with [bold]Remnawave[/bold] -- a new panel")
    err_console.print("  with multi-node fleet management. Migration is a fresh deploy;")
    err_console.print("  old 3x-ui data is not transferred automatically.")
    err_console.print()

    err_console.print("  [bold]Step 1:[/bold] Deploy Remnawave on your first server")
    first_ip = server_data[0]["ip"]
    err_console.print(f"    [cyan]meridian deploy {first_ip}[/cyan]")
    err_console.print()

    err_console.print("  [bold]Step 2:[/bold] Re-create your clients")
    all_clients: list[str] = []
    for s in server_data:
        all_clients.extend(s["clients"])  # type: ignore[arg-type]
    if all_clients:
        for name in all_clients:
            err_console.print(f"    [cyan]meridian client add {name}[/cyan]")
    else:
        err_console.print("    [cyan]meridian client add NAME[/cyan]")
    err_console.print()

    err_console.print("  [bold]Step 3:[/bold] Clients re-scan QR codes")
    err_console.print("    Connection URLs change with Remnawave. Each client needs")
    err_console.print("    to scan a new QR code via [cyan]meridian client show NAME[/cyan].")
    err_console.print()

    if total_relays > 0:
        err_console.print("  [bold]Step 4:[/bold] Re-deploy relays")
        for s in server_data:
            for relay_ip, relay_name in s["relays"]:  # type: ignore[misc]
                name_flag = f" --name {relay_name}" if relay_name else ""
                err_console.print(f"    [cyan]meridian relay deploy {relay_ip} --exit {s['ip']}{name_flag}[/cyan]")
        err_console.print()

    warn("Old 3x-ui credentials are preserved in ~/.meridian/credentials/ as a backup.")
    err_console.print()
    ok("Review the steps above, then start with 'meridian deploy'")
    err_console.print()
