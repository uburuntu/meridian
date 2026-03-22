"""Meridian CLI — main Typer application."""

from __future__ import annotations

import typer

from meridian import __version__
from meridian.console import banner

app = typer.Typer(
    name="meridian",
    help="Censorship-resistant proxy server management",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Subcommand groups
client_app = typer.Typer(help="Manage proxy clients", no_args_is_help=True)
server_app = typer.Typer(help="Manage known servers", no_args_is_help=True)
relay_app = typer.Typer(help="Manage relay nodes", no_args_is_help=True)
app.add_typer(client_app, name="client")
app.add_typer(server_app, name="server")
app.add_typer(relay_app, name="relay")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
) -> None:
    """Meridian — Censorship-resistant proxy server management."""
    if ctx.resilient_parsing:
        return

    if version:
        print(f"meridian {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        raise typer.Exit()

    # Show banner before subcommands (but not for --help)
    import sys

    if "--help" not in sys.argv and "-h" not in sys.argv:
        banner(__version__)

    # Auto-update check (skip for meta commands)
    if ctx.invoked_subcommand not in ("update",):
        from meridian.update import check_for_update

        check_for_update(__version__)


# =============================================================================
# Deploy
# =============================================================================


@app.command("deploy")
def deploy_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    domain: str = typer.Option(
        "",
        "--domain",
        "-d",
        help="CDN fallback via Cloudflare (guide: getmeridian.org/docs/en/domain-mode/)",
    ),
    email: str = typer.Option("", "--email", help="Email for TLS certificate notifications"),
    sni: str = typer.Option(
        "",
        "--sni",
        "-s",
        help="Camouflage target (default: www.microsoft.com). Use 'meridian scan' for optimal",
    ),
    xhttp: bool = typer.Option(
        True,
        "--xhttp/--no-xhttp",
        help="XHTTP fallback transport (on by default, routed through port 443)",
    ),
    name: str = typer.Option("", "--name", help="Name for the first client (default: 'default')"),
    user: str = typer.Option("root", "--user", "-u", help="SSH user on the server"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip all prompts (use defaults)"),
    server: str = typer.Option("", "--server", help="Target server name or IP (for re-deploys)"),
) -> None:
    """Deploy a VLESS+Reality proxy server. Interactive wizard if no IP provided.

    [dim]Examples:[/dim]
      [cyan]meridian deploy[/cyan]                          Interactive wizard
      [cyan]meridian deploy 1.2.3.4[/cyan]                  Deploy with defaults
      [cyan]meridian deploy 1.2.3.4 --domain d.io[/cyan]    CDN fallback via Cloudflare
      [cyan]meridian deploy 1.2.3.4 --no-xhttp[/cyan]       Reality only, no XHTTP
    """
    from meridian.commands.setup import run

    run(ip, domain, email, sni, xhttp, name, user, yes, server)


# =============================================================================
# Client
# =============================================================================


@client_app.command("add")
def client_add(
    name: str = typer.Argument(..., help="Client name"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
) -> None:
    """Add a new client."""
    from meridian.commands.client import run_add

    run_add(name, user, server)


@client_app.command("list")
def client_list_cmd(
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
) -> None:
    """List all clients."""
    from meridian.commands.client import run_list

    run_list(user, server)


@client_app.command("remove")
def client_remove(
    name: str = typer.Argument(..., help="Client name"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
) -> None:
    """Remove a client."""
    from meridian.commands.client import run_remove

    run_remove(name, user, server)


# =============================================================================
# Server
# =============================================================================


@server_app.command("add")
def server_add_cmd(
    ip: str = typer.Argument(..., help="Server IP address"),
    name: str = typer.Option("", "--name", help="Display name"),
    user: str = typer.Option("root", "--user", "-u", help="SSH user"),
) -> None:
    """Add a known server."""
    from meridian.commands.server import run_add

    run_add(ip, name, user)


@server_app.command("list")
def server_list_cmd() -> None:
    """List known servers."""
    from meridian.commands.server import run_list

    run_list()


@server_app.command("remove")
def server_remove_cmd(
    query: str = typer.Argument(..., help="Server IP or name"),
) -> None:
    """Remove a known server."""
    from meridian.commands.server import run_remove

    run_remove(query)


# =============================================================================
# Preflight / Scan / Test
# =============================================================================


@app.command("preflight")
def preflight_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    domain: str = typer.Option("", "--domain", "-d", help="Domain to check"),
    sni: str = typer.Option("", "--sni", "-s", help="SNI target to verify"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
    ai: bool = typer.Option(False, "--ai", help="Copy AI-ready prompt to clipboard for ChatGPT/Claude"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
) -> None:
    """Validate server compatibility (SNI, ports, DNS, OS, disk, ASN) before deploying."""
    from meridian.commands.check import run

    run(ip, domain, sni, user, ai, server)


@app.command("scan")
def scan_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
) -> None:
    """Find optimal SNI targets via RealiTLScanner."""
    from meridian.commands.scan import run

    run(ip, user, server)


@app.command("test")
def test_cmd(
    ip: str = typer.Argument("", help="Server IP to test connectivity to"),
    domain: str = typer.Option("", "--domain", "-d", help="Domain to test"),
    sni: str = typer.Option("", "--sni", "-s", help="SNI target to test"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
) -> None:
    """Test proxy reachability from client device (no SSH required)."""
    from meridian.commands.ping import run

    run(ip, domain, sni, server)


# =============================================================================
# Doctor / Teardown / Update
# =============================================================================


@app.command("doctor")
def doctor_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    sni: str = typer.Option("", "--sni", "-s", help="SNI target"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
    ai: bool = typer.Option(False, "--ai", help="Copy AI-ready prompt to clipboard for ChatGPT/Claude"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
) -> None:
    """Collect system info for bug reports. Use --ai for ChatGPT/Claude prompt."""
    from meridian.commands.diagnostics import run

    run(ip, sni, user, ai, server)


# Alias: rage → doctor
@app.command("rage", hidden=True)
def rage_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    sni: str = typer.Option("", "--sni", "-s", help="SNI target"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
    ai: bool = typer.Option(False, "--ai", help="Copy AI-ready prompt to clipboard for ChatGPT/Claude"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
) -> None:
    """Alias for doctor."""
    from meridian.commands.diagnostics import run

    run(ip, sni, user, ai, server)


@app.command("teardown")
def teardown_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    user: str = typer.Option("", "--user", "-u", help="SSH user (default: from server registry)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    server: str = typer.Option("", "--server", help="Target server (name or IP)"),
) -> None:
    """Remove proxy deployment from server."""
    from meridian.commands.uninstall import run

    run(ip, user, yes, server)


@app.command("update")
def update_cmd() -> None:
    """Update meridian to the latest version."""
    from meridian.update import run_self_update

    run_self_update()


# =============================================================================
# Relay
# =============================================================================


@relay_app.command("deploy")
def relay_deploy_cmd(
    relay_ip: str = typer.Argument(..., help="Relay server IP address"),
    exit: str = typer.Option(..., "--exit", "-e", help="Exit server (IP or name)"),
    user: str = typer.Option("root", "--user", "-u", help="SSH user on the relay"),
    name: str = typer.Option("", "--name", help="Friendly name for the relay (e.g., ru-moscow)"),
    port: int = typer.Option(443, "--port", "-p", help="Relay listen port"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Deploy a TCP relay that forwards to an exit server.

    [dim]Examples:[/dim]
      [cyan]meridian relay deploy 1.2.3.4 --exit 5.6.7.8[/cyan]
      [cyan]meridian relay deploy 1.2.3.4 --exit myserver --name ru-moscow[/cyan]
    """
    from meridian.commands.relay import run_deploy

    run_deploy(relay_ip, exit, user, name, port, yes)


@relay_app.command("list")
def relay_list_cmd(
    exit: str = typer.Option("", "--exit", "-e", help="Filter by exit server (IP or name)"),
    user: str = typer.Option("", "--user", "-u", help="SSH user"),
) -> None:
    """List relay nodes."""
    from meridian.commands.relay import run_list

    run_list(exit, user)


@relay_app.command("remove")
def relay_remove_cmd(
    relay_ip: str = typer.Argument(..., help="Relay IP to remove"),
    exit: str = typer.Option("", "--exit", "-e", help="Exit server (IP or name)"),
    user: str = typer.Option("", "--user", "-u", help="SSH user"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a relay node."""
    from meridian.commands.relay import run_remove

    run_remove(relay_ip, exit, user, yes)


@relay_app.command("check")
def relay_check_cmd(
    relay_ip: str = typer.Argument(..., help="Relay IP to check"),
    exit: str = typer.Option("", "--exit", "-e", help="Exit server (IP or name)"),
    user: str = typer.Option("", "--user", "-u", help="SSH user"),
) -> None:
    """Check health of a relay node."""
    from meridian.commands.relay import run_check

    run_check(relay_ip, exit, user)
