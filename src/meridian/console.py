"""Rich-based terminal output helpers."""

from __future__ import annotations

from typing import NoReturn

import typer
from rich.console import Console
from rich.theme import Theme

_theme = Theme(
    {
        "info": "cyan",
        "ok": "green",
        "warn": "yellow",
        "error": "red bold",
        "dim": "dim",
    }
)

console = Console(theme=_theme, highlight=False)
err_console = Console(theme=_theme, stderr=True, highlight=False)


def info(msg: str) -> None:
    err_console.print(f"  [info]\u2192[/info] {msg}")


def ok(msg: str) -> None:
    err_console.print(f"  [ok]\u2713[/ok] {msg}")


def warn(msg: str) -> None:
    err_console.print(f"  [warn]![/warn] {msg}")


def fail(msg: str) -> NoReturn:
    err_console.print(f"\n  [error]\u2717 {msg}[/error]")
    err_console.print("  [dim]Not connecting? Run: meridian ping | Other issues? Run: meridian diagnostics --ai[/dim]")
    err_console.print("  [dim]Report: https://github.com/uburuntu/meridian/issues[/dim]\n")
    raise typer.Exit(code=1)


def line() -> None:
    dash = "\u2500"
    err_console.print(f"  [dim]{dash * 41}[/dim]")


def banner(version: str) -> None:
    err_console.print(f"\n  [bold]Meridian[/bold] [dim]v{version}[/dim]\n")


def prompt(message: str, default: str = "") -> str:
    """Interactive prompt that reads from /dev/tty for pipe safety."""
    suffix = f" [{default}]" if default else ""
    try:
        # Read from /dev/tty to work even when stdin is piped
        tty = open("/dev/tty", "r")
        err_console.print(f"  [info]\u2192[/info] {message}{suffix}: ", end="")
        value = tty.readline().strip()
        tty.close()
    except OSError:
        # No TTY available (CI, non-interactive)
        value = ""
    return value or default


def confirm(message: str = "Press Enter to continue...") -> None:
    """Wait for user to press Enter."""
    try:
        tty = open("/dev/tty", "r")
        err_console.print(f"\n  [dim]{message}[/dim]", end="")
        tty.readline()
        tty.close()
    except OSError:
        pass
