"""Meridian — Censorship-resistant proxy server management."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("meridian-vpn")
except PackageNotFoundError:
    # Running from source without install
    from pathlib import Path

    _version_file = Path(__file__).parent.parent.parent / "VERSION"
    __version__ = _version_file.read_text().strip() if _version_file.exists() else "0.0.0-dev"
