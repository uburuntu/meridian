"""Service-layer use cases for meridian-core."""

from meridian.core.services.fleet import (
    FleetInventoryServiceResult,
    FleetStatusServiceResult,
    collect_fleet_inventory,
    collect_fleet_status,
)

__all__ = [
    "FleetInventoryServiceResult",
    "FleetStatusServiceResult",
    "collect_fleet_inventory",
    "collect_fleet_status",
]
