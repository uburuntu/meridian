"""Schema migration for cluster.yml.

Applies versioned transformations to cluster data. Each migration
function takes a data dict (version N) and returns version N+1.
"""

from __future__ import annotations

from typing import Any

CURRENT_VERSION = 2


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate cluster.yml data to the current version.

    Applies all migrations in sequence from the data's version to
    CURRENT_VERSION. Returns the data unchanged if already current
    or newer (forward-compat).
    """
    version = data.get("version", 1)
    if version >= CURRENT_VERSION:
        return data

    migrations: dict[int, Any] = {
        1: _migrate_v1_to_v2,
    }

    while version < CURRENT_VERSION:
        migrator = migrations.get(version)
        if migrator is None:
            break
        data = migrator(data)
        version += 1
        data["version"] = version

    return data


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate cluster.yml from v1 to v2.

    v2 adds: subscription_page config, desired state fields
    (desired_nodes, desired_clients, desired_relays).

    Subscription page is disabled by default for existing v1 deployments
    (they were deployed without it). Desired state fields are left empty
    (v1 clusters are managed imperatively).
    """
    # Subscription page: disabled for existing deployments
    if "subscription_page" not in data:
        data["subscription_page"] = {"enabled": False}

    # Desired state fields: empty by default (no breaking change)
    # These are optional — omitting them is valid.

    return data
