"""Paths, URLs, and constants."""

from __future__ import annotations

import os
import platform
from pathlib import Path

MERIDIAN_HOME = Path(os.environ.get("MERIDIAN_HOME", Path.home() / ".meridian"))
CREDS_BASE = MERIDIAN_HOME / "credentials"
CACHE_DIR = MERIDIAN_HOME / "cache"
SERVERS_FILE = MERIDIAN_HOME / "servers"
SERVER_CREDS_DIR = Path("/etc/meridian")

PYPI_PACKAGE = "meridian-vpn"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"
AI_DOCS_URL = "https://meridian.msu.rocks/ai/reference.md"
GITHUB_REPO = "https://github.com/uburuntu/meridian"
GITHUB_ISSUES = f"{GITHUB_REPO}/issues"

# Update throttle (seconds)
UPDATE_CHECK_INTERVAL = 60


def is_macos() -> bool:
    return platform.system() == "Darwin"


def ensure_dirs() -> None:
    """Create standard directories with proper permissions."""
    MERIDIAN_HOME.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CREDS_BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
