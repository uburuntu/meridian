"""Paths, URLs, and constants."""

from __future__ import annotations

import os
from pathlib import Path

MERIDIAN_HOME = Path(os.environ.get("MERIDIAN_HOME", Path.home() / ".meridian"))
CREDS_BASE = MERIDIAN_HOME / "credentials"
CACHE_DIR = MERIDIAN_HOME / "cache"
SERVERS_FILE = MERIDIAN_HOME / "servers"
SERVER_CREDS_DIR = Path("/etc/meridian")

DEFAULT_SNI = "www.microsoft.com"
DEFAULT_FINGERPRINT = "chrome"
DEFAULT_PANEL_PORT = 2053

PYPI_PACKAGE = "meridian-vpn"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"
GITHUB_REPO = "https://github.com/uburuntu/meridian"
GITHUB_ISSUES = f"{GITHUB_REPO}/issues"
WEBSITE_URL = "https://getmeridian.org"

# Update throttle (seconds)
UPDATE_CHECK_INTERVAL = 60

# Relay (Realm TCP relay)
REALM_VERSION = "2.9.3"
REALM_GITHUB_URL = "https://github.com/zhboner/realm/releases/download"
RELAY_SERVICE_NAME = "meridian-relay"

# SHA256 digests for Realm tarball verification (keyed by target triple)
REALM_SHA256: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "2eba86f1a1e47c1bfe9d6fd682ef8667bd05e57c3aeb0ec37806aabe2ce74a0c",
    "aarch64-unknown-linux-gnu": "9937daacdcdfcac9fd78d25819f2de0a5c3357c2c49e686679d812343ab8661e",
}
RELAY_CONFIG_PATH = "/etc/meridian/realm.toml"


def is_ipv4(s: str) -> bool:
    """Check if string looks like an IPv4 address."""
    parts = s.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
