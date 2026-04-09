"""Auto-update mechanism via PyPI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

from meridian.config import (
    CACHE_DIR,
    GITHUB_REPO,
    PYPI_JSON_URL,
    PYPI_PACKAGE,
    UPDATE_CHECK_INTERVAL,
)
from meridian.console import err_console, info, ok, warn

_RELEASES_URL = f"{GITHUB_REPO}/releases"
_INSTALL_CMD = "curl -sSf https://getmeridian.org/install.sh | bash"


def get_pypi_latest() -> str | None:
    """Fetch latest version from PyPI JSON API."""
    try:
        req = urllib.request.Request(PYPI_JSON_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except (OSError, ValueError, KeyError):
        return None


def _should_check() -> bool:
    """Return True if enough time has passed since last check."""
    check_file = CACHE_DIR / "last_update_check"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if check_file.exists():
        try:
            last_check = int(check_file.read_text().strip() or "0")
            if time.time() - last_check < UPDATE_CHECK_INTERVAL:
                return False
        except (ValueError, OSError):
            pass

    check_file.write_text(str(int(time.time())))
    return True


def check_for_update(current_version: str) -> None:
    """Check PyPI for updates and surface them without auto-upgrading."""
    if not _should_check():
        return

    latest = get_pypi_latest()
    if not latest or latest == current_version:
        return

    try:
        current = Version(current_version)
        remote = Version(latest)
    except InvalidVersion:
        return

    if remote <= current:
        return  # running dev/pre-release, don't downgrade

    if current.major == remote.major and current.minor == remote.minor:
        err_console.print(f"\n  [warn]v{latest} available[/warn]")
        err_console.print(f"  [dim]Patch release: {_RELEASES_URL}[/dim]")
        err_console.print(
            "  [dim]Run[/dim] [bold]meridian update[/bold] [dim]when ready, then[/dim] "
            "[bold]meridian deploy[/bold] [dim]to apply[/dim]\n"
        )
    elif current.major != remote.major:
        # Major: review before updating
        err_console.print(f"\n  [bold red]v{latest} available (major release)[/bold red]")
        err_console.print(f"  [dim]Review changes before updating: {_RELEASES_URL}[/dim]")
        err_console.print("  [dim]After updating, run[/dim] [bold]meridian deploy[/bold] [dim]to apply[/dim]\n")
    else:
        # Minor: inform, link to changelog
        err_console.print(f"\n  [warn]v{latest} available[/warn]")
        err_console.print(f"  [dim]See what's new: {_RELEASES_URL}[/dim]")
        err_console.print(
            "  [dim]Run[/dim] [bold]meridian update[/bold] [dim]then[/dim] "
            "[bold]meridian deploy[/bold] [dim]to apply[/dim]\n"
        )


def do_upgrade() -> bool:
    """Upgrade via uv > pipx > pip3."""
    success = False

    if shutil.which("uv"):
        result = subprocess.run(
            ["uv", "tool", "upgrade", PYPI_PACKAGE],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            success = True

    if not success and shutil.which("pipx"):
        result = subprocess.run(
            ["pipx", "upgrade", PYPI_PACKAGE],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            success = True

    if not success and shutil.which("pip3"):
        # Try --user first, then --break-system-packages for PEP 668
        for extra_args in [["--user"], ["--user", "--break-system-packages"]]:
            result = subprocess.run(
                ["pip3", "install", "--upgrade", *extra_args, PYPI_PACKAGE],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                success = True
                break

    if success:
        _refresh_symlink()

    return success


def _refresh_symlink() -> None:
    """Re-create /usr/local/bin/meridian symlink after upgrade."""
    meridian_bin = shutil.which("meridian")
    if not meridian_bin or meridian_bin == "/usr/local/bin/meridian":
        return
    symlink = Path("/usr/local/bin/meridian")
    if not symlink.is_symlink():
        return
    # Only refresh if the symlink already exists (install.sh created it)
    try:
        subprocess.run(
            ["sudo", "-n", "ln", "-sf", meridian_bin, "/usr/local/bin/meridian"],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def run_self_update() -> None:
    """Explicit self-update command."""
    info("Checking for updates...")
    latest = get_pypi_latest()

    if not latest:
        warn("Could not reach PyPI to check for updates")
        return

    from meridian import __version__

    try:
        current = Version(__version__)
        remote = Version(latest)
    except InvalidVersion:
        warn("Could not parse version numbers")
        return

    if remote <= current:
        ok(f"Already on the latest version (v{__version__})")
        return

    # Version-level context
    if current.major != remote.major:
        warn(f"Major release v{latest} — review changes before redeploying:")
        info(_RELEASES_URL)
    elif current.minor != remote.minor:
        info(f"v{latest} available. What's new: {_RELEASES_URL}")

    info(f"Updating v{__version__} → v{latest}...")
    if do_upgrade():
        ok(f"Updated to v{latest}")
        info("Run `meridian deploy` to apply changes to your servers")
    else:
        warn("Could not upgrade automatically. Try reinstalling:")
        info(_INSTALL_CMD)
