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


def fail(msg: str, *, hint: str = "", hint_type: str = "bug") -> NoReturn:
    """Print an error message and exit with code 1.

    Args:
        msg: The error message to display.
        hint: Optional hint shown below the error.
        hint_type: Controls the footer line shown:
            "user"   -- input validation errors; no GitHub link shown.
            "system" -- infrastructure errors; suggests 'meridian doctor'.
            "bug"    -- unexpected errors (default); shows GitHub issues link.
    """
    err_console.print(f"\n  [error]\u2717 {msg}[/error]")
    if hint:
        err_console.print(f"  [dim]{hint}[/dim]")
    if hint_type == "user":
        err_console.print()
    elif hint_type == "system":
        err_console.print("  [dim]Run: meridian doctor  (to collect server info)[/dim]\n")
    else:  # "bug"
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
        with open("/dev/tty") as tty:
            err_console.print(f"  [info]\u2192[/info] {message}{suffix}: ", end="")
            value = tty.readline().strip()
    except OSError:
        # No TTY available (CI, non-interactive)
        value = ""
    return value or default


def confirm(message: str = "Continue?") -> bool:
    """Y/n confirmation prompt. Returns True on accept, raises typer.Exit(1) on reject.

    Accepts: y, Y, Enter (default yes).
    Rejects: n, N (raises typer.Exit(1)).
    """
    try:
        with open("/dev/tty") as tty:
            err_console.print(f"\n  [info]\u2192[/info] {message} [dim][Y/n][/dim] ", end="")
            answer = tty.readline().strip().lower()
    except OSError:
        # No TTY available — default to reject (don't auto-confirm destructive ops)
        raise typer.Exit(code=1)
    if answer in ("", "y", "yes"):
        return True
    raise typer.Exit(code=1)
