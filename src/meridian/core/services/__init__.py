"""Service-layer use cases for meridian-core."""

from meridian.core.services.clients import (
    ClientListServiceResult,
    ClientNotFoundError,
    ClientShowServiceResult,
    collect_client_list,
    collect_client_show,
)
from meridian.core.services.fleet import (
    FleetInventoryServiceResult,
    FleetStatusServiceResult,
    collect_fleet_inventory,
    collect_fleet_status,
)

__all__ = [
    "ClientListServiceResult",
    "ClientNotFoundError",
    "ClientShowServiceResult",
    "FleetInventoryServiceResult",
    "FleetStatusServiceResult",
    "collect_client_list",
    "collect_client_show",
    "collect_fleet_inventory",
    "collect_fleet_status",
]
