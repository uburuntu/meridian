"""Meridian CLI — main Typer application."""

from __future__ import annotations

import typer

from meridian import __version__
from meridian.console import banner

app = typer.Typer(
    name="meridian",
    help="Censorship-resistant proxy server management",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Subcommand groups
client_app = typer.Typer(help="Manage proxy clients", no_args_is_help=True)
server_app = typer.Typer(help="Manage known servers", no_args_is_help=True)
app.add_typer(client_app, name="client")
app.add_typer(server_app, name="server")

# Global state for --server flag (passed via ctx.obj)
_global_server: str = ""


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    server: str = typer.Option("", "--server", help="Target a specific configured server"),
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
) -> None:
    """Meridian — Censorship-resistant proxy server management."""
    global _global_server
    _global_server = server

    if version:
        banner(__version__)
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        banner(__version__)
        raise typer.Exit()

    # Show banner before subcommands
    banner(__version__)

    # Auto-update check (skip for meta commands)
    if ctx.invoked_subcommand not in ("self-update", "version"):
        from meridian.update import check_for_update

        check_for_update(__version__)


@app.command("version")
def version_cmd() -> None:
    """Show meridian version."""
    from rich import print as rprint

    rprint(f"  meridian {__version__}")


@app.command("setup")
def setup_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    domain: str = typer.Option("", "--domain", help="Add CDN fallback via Cloudflare"),
    sni: str = typer.Option("", "--sni", help="Reality camouflage target"),
    xhttp: bool = typer.Option(False, "--xhttp", help="Add XHTTP transport"),
    name: str = typer.Option("", "--name", help="Name the first client"),
    user: str = typer.Option("root", "--user", help="SSH user"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip prompts"),
) -> None:
    """Deploy proxy server."""
    from meridian.commands.setup import run

    run(ip, domain, sni, xhttp, name, user, yes, _global_server)


@client_app.command("add")
def client_add(
    name: str = typer.Argument(..., help="Client name"),
    user: str = typer.Option("root", "--user", help="SSH user"),
) -> None:
    """Add a new client."""
    from meridian.commands.client import run_add

    run_add(name, user, _global_server)


@client_app.command("list")
def client_list_cmd(
    user: str = typer.Option("root", "--user", help="SSH user"),
) -> None:
    """List all clients."""
    from meridian.commands.client import run_list

    run_list(user, _global_server)


@client_app.command("remove")
def client_remove(
    name: str = typer.Argument(..., help="Client name"),
    user: str = typer.Option("root", "--user", help="SSH user"),
) -> None:
    """Remove a client."""
    from meridian.commands.client import run_remove

    run_remove(name, user, _global_server)


@server_app.command("add")
def server_add_cmd(
    ip: str = typer.Argument(..., help="Server IP address"),
    name: str = typer.Option("", "--name", help="Display name"),
    user: str = typer.Option("root", "--user", help="SSH user"),
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


@app.command("check")
def check_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    domain: str = typer.Option("", "--domain", help="Domain to check"),
    sni: str = typer.Option("", "--sni", help="SNI target to verify"),
    user: str = typer.Option("root", "--user", help="SSH user"),
    ai: bool = typer.Option(False, "--ai", help="Build AI-ready diagnostic prompt"),
) -> None:
    """Pre-flight server validation."""
    from meridian.commands.check import run

    run(ip, domain, sni, user, ai, _global_server)


@app.command("scan")
def scan_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    user: str = typer.Option("root", "--user", help="SSH user"),
) -> None:
    """Find optimal SNI targets via RealiTLScanner."""
    from meridian.commands.scan import run

    run(ip, user, _global_server)


@app.command("ping")
def ping_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    domain: str = typer.Option("", "--domain", help="Domain to test"),
    sni: str = typer.Option("", "--sni", help="SNI target to test"),
) -> None:
    """Test proxy reachability from client device."""
    from meridian.commands.ping import run

    run(ip, domain, sni, _global_server)


@app.command("diagnostics")
def diagnostics_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    sni: str = typer.Option("", "--sni", help="SNI target"),
    user: str = typer.Option("root", "--user", help="SSH user"),
    ai: bool = typer.Option(False, "--ai", help="Build AI-ready diagnostic prompt"),
) -> None:
    """Collect system info for bug reports."""
    from meridian.commands.diagnostics import run

    run(ip, sni, user, ai, _global_server)


@app.command("uninstall")
def uninstall_cmd(
    ip: str = typer.Argument("", help="Server IP address"),
    user: str = typer.Option("root", "--user", help="SSH user"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove proxy from server."""
    from meridian.commands.uninstall import run

    run(ip, user, yes, _global_server)


@app.command("self-update")
def self_update_cmd() -> None:
    """Update meridian to the latest version."""
    from meridian.update import run_self_update

    run_self_update()
