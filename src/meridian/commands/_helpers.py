"""Shared helpers for command modules.

Common patterns used across multiple command files: cluster loading,
panel client creation, and traffic formatting.
"""

from __future__ import annotations

from meridian.cluster import ClusterConfig
from meridian.console import fail
from meridian.remnawave import MeridianPanel


def load_cluster() -> ClusterConfig:
    """Load and validate cluster configuration. Exits if not configured."""
    cluster = ClusterConfig.load()
    if not cluster.is_configured:
        fail(
            "No cluster configured",
            hint="Deploy first: meridian deploy",
            hint_type="user",
        )
    return cluster


def make_panel(cluster: ClusterConfig) -> MeridianPanel:
    """Create a MeridianPanel client from cluster config."""
    return MeridianPanel(cluster.panel.url, cluster.panel.api_token)


def format_traffic(bytes_used: int, bytes_limit: int = 0) -> str:
    """Format traffic usage as a human-readable string."""

    def _human(b: int) -> str:
        if b <= 0:
            return "0 B"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(b) < 1024:
                return f"{b:.1f} {unit}" if unit != "B" else f"{b} {unit}"
            b /= 1024  # type: ignore[assignment]
        return f"{b:.1f} PB"

    used = _human(bytes_used)
    if bytes_limit > 0:
        return f"{used} / {_human(bytes_limit)}"
    return used
