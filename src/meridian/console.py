"""Rich-based terminal output helpers."""

from __future__ import annotations

import json as _json
from typing import Any, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
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

_output_json = False


def set_json_mode(enabled: bool) -> None:
    """Set JSON output mode."""
    global _output_json
    _output_json = enabled


def is_json_mode() -> bool:
    """Check if JSON output mode is active."""
    return _output_json


def json_output(data: Any) -> None:
    """Write JSON to stdout (for --json mode). Separate from Rich stderr output."""
    print(_json.dumps(data, indent=2, default=str))


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
    # Escape message and suffix to prevent Rich from parsing [y/N] etc. as markup
    escaped = escape(f"{message}{suffix}")
    try:
        with open("/dev/tty") as tty:
            err_console.print(f"  [info]\u2192[/info] {escaped}: ", end="")
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


def choose(message: str, options: list[str], *, default: int = 1) -> int:
    """Numbered choice prompt. Returns 1-based index of selected option.

    Displays numbered options, then prompts for selection.
    Falls back to default on empty input or invalid choice.
    """
    for i, opt in enumerate(options, 1):
        err_console.print(f"    {i}. {opt}")
    err_console.print()
    answer = prompt(f"{message}, or press Enter for ({default})")
    if not answer:
        return default
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return int(answer)
    return default
