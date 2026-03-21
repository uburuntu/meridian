"""Auto-update mechanism via PyPI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import warnings
from pathlib import Path

from packaging.version import Version

from meridian.config import CACHE_DIR, PYPI_JSON_URL, PYPI_PACKAGE, UPDATE_CHECK_INTERVAL
from meridian.console import err_console, info, ok, warn


def get_pypi_latest() -> str | None:
    """Fetch latest version from PyPI JSON API."""
    try:
        req = urllib.request.Request(PYPI_JSON_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception as e:
        warnings.warn(f"Could not fetch latest version from PyPI: {e}", stacklevel=2)
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
    """Check PyPI for updates. Auto-upgrade patches, prompt for minor/major."""
    if not _should_check():
        return

    latest = get_pypi_latest()
    if not latest or latest == current_version:
        return

    try:
        current = Version(current_version)
        remote = Version(latest)
    except Exception as e:
        warnings.warn(f"Could not parse version for update check: {e}", stacklevel=2)
        return

    if remote <= current:
        return  # running dev/pre-release, don't downgrade

    if current.major == remote.major and current.minor == remote.minor:
        # Patch: auto-upgrade silently
        if do_upgrade():
            ok(f"Auto-updated: v{current_version} → v{latest}")
            # Re-exec so new version runs
            os.execvp(sys.argv[0], sys.argv)
    else:
        # Minor/major: prompt
        err_console.print(f"\n  [warn]Update available:[/warn] v{current_version} → v{latest}")
        err_console.print("  Run: [bold]meridian self-update[/bold]\n")


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
    except Exception as e:
        warnings.warn(f"Could not parse version numbers: {e}", stacklevel=2)
        warn("Could not parse version numbers")
        return

    if remote <= current:
        ok(f"Already on the latest version (v{__version__})")
        return

    info(f"Updating v{__version__} → v{latest}...")
    if do_upgrade():
        ok(f"Updated to v{latest}")
        info("Restart meridian to use the new version")
    else:
        warn(f"Could not upgrade automatically. Try: uv tool upgrade {PYPI_PACKAGE}")
