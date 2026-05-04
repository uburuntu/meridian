"""Fleet service use cases with injectable infrastructure adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, Self

from meridian.core.fleet import (
    ApiNodeLike,
    ApiUserLike,
    FleetInventory,
    FleetSources,
    FleetStatus,
    FleetTopology,
    TopologyRelay,
    build_fleet_inventory,
    build_fleet_status,
)
from meridian.core.models import MeridianError

PanelErrorKind = Literal["auth", "system"]


class FleetPanelClient(Protocol):
    """Panel operations needed by fleet service use cases."""

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> object: ...

    def ping(self) -> bool: ...

    def list_nodes(self) -> Sequence[ApiNodeLike]: ...

    def list_users(self) -> Sequence[ApiUserLike]: ...


PanelErrorClassifier = Callable[[Exception], PanelErrorKind]
RelayHealthChecker = Callable[[list[TopologyRelay]], Mapping[tuple[str, int], bool]]


@dataclass(frozen=True)
class FleetStatusServiceResult:
    """Status result plus non-fatal collection warnings."""

    status: FleetStatus
    warnings: list[MeridianError]


@dataclass(frozen=True)
class FleetInventoryServiceResult:
    """Inventory result plus non-fatal collection warnings."""

    inventory: FleetInventory
    warnings: list[MeridianError]


def _system_warning(
    code: str,
    message: str,
    *,
    hint: str = "",
    details: dict[str, object] | None = None,
) -> MeridianError:
    """Build a retryable system warning for partial fleet data."""
    return MeridianError(
        code=code,
        category="system",
        message=message,
        hint=hint,
        retryable=True,
        exit_code=3,
        details=details or {},
    )


def _handle_error(exc: Exception, classify_error: PanelErrorClassifier) -> None:
    """Reraise auth errors; keep system errors as partial observations."""
    if classify_error(exc) == "auth":
        raise exc


def collect_fleet_inventory(
    topology: FleetTopology,
    panel_client: FleetPanelClient,
    *,
    classify_error: PanelErrorClassifier,
) -> FleetInventoryServiceResult:
    """Collect redacted fleet inventory with live panel node observations."""
    panel_ok = False
    api_nodes: Sequence[ApiNodeLike] = []
    warnings: list[MeridianError] = []
    sources = FleetSources(panel="unknown", nodes="not_requested", users="not_requested", relays="not_requested")

    try:
        with panel_client as panel:
            panel_ok = panel.ping()
            sources = sources.model_copy(update={"panel": "available" if panel_ok else "unavailable"})
            if not panel_ok:
                warnings.append(
                    _system_warning(
                        "MERIDIAN_PANEL_UNREACHABLE",
                        "Cannot reach panel API; live inventory status is unavailable",
                        hint="Check panel connectivity and run meridian doctor.",
                    )
                )
                sources = sources.model_copy(update={"nodes": "unavailable"})
            else:
                try:
                    api_nodes = panel.list_nodes()
                    sources = sources.model_copy(update={"nodes": "available"})
                except Exception as exc:
                    _handle_error(exc, classify_error)
                    sources = sources.model_copy(update={"nodes": "unavailable"})
                    warnings.append(
                        _system_warning(
                            "MERIDIAN_PANEL_NODES_UNAVAILABLE",
                            "Could not fetch node status from panel",
                            hint="Panel is reachable, but the node list API failed.",
                            details={"cause": type(exc).__name__},
                        )
                    )
    except Exception as exc:
        _handle_error(exc, classify_error)
        panel_ok = False
        sources = sources.model_copy(update={"panel": "unavailable", "nodes": "unavailable"})
        warnings.append(
            _system_warning(
                "MERIDIAN_PANEL_UNREACHABLE",
                "Cannot reach panel API; live inventory status is unavailable",
                hint="Check panel connectivity and run meridian doctor.",
                details={"cause": type(exc).__name__},
            )
        )

    return FleetInventoryServiceResult(
        inventory=build_fleet_inventory(topology, panel_healthy=panel_ok, api_nodes=api_nodes, sources=sources),
        warnings=warnings,
    )


def collect_fleet_status(
    topology: FleetTopology,
    panel_client: FleetPanelClient,
    *,
    check_relays: RelayHealthChecker,
    classify_error: PanelErrorClassifier,
) -> FleetStatusServiceResult:
    """Collect fleet health overview with partial-failure warnings."""
    panel_ok = False
    api_nodes: Sequence[ApiNodeLike] = []
    api_users: Sequence[ApiUserLike] = []
    warnings: list[MeridianError] = []
    relay_source: Literal["available", "not_requested"] = "available" if topology.relays else "not_requested"
    sources = FleetSources(panel="unknown", nodes="not_requested", users="not_requested", relays=relay_source)

    try:
        with panel_client as panel:
            panel_ok = panel.ping()
            sources = sources.model_copy(update={"panel": "available" if panel_ok else "unavailable"})
            if not panel_ok:
                warnings.append(
                    _system_warning(
                        "MERIDIAN_PANEL_UNREACHABLE",
                        "Cannot reach panel API -- node and user data may be stale",
                        hint="Check panel connectivity and run meridian doctor.",
                    )
                )
                sources = sources.model_copy(update={"nodes": "unavailable", "users": "unavailable"})
            else:
                try:
                    api_nodes = panel.list_nodes()
                    sources = sources.model_copy(update={"nodes": "available"})
                except Exception as exc:
                    _handle_error(exc, classify_error)
                    sources = sources.model_copy(update={"nodes": "unavailable"})
                    warnings.append(
                        _system_warning(
                            "MERIDIAN_PANEL_NODES_UNAVAILABLE",
                            "Could not fetch node status from panel",
                            hint="Panel is reachable, but the node list API failed.",
                            details={"cause": type(exc).__name__},
                        )
                    )
                try:
                    api_users = panel.list_users()
                    sources = sources.model_copy(update={"users": "available"})
                except Exception as exc:
                    _handle_error(exc, classify_error)
                    sources = sources.model_copy(update={"users": "unavailable"})
                    warnings.append(
                        _system_warning(
                            "MERIDIAN_PANEL_USERS_UNAVAILABLE",
                            "Could not fetch user status from panel",
                            hint="Panel is reachable, but the user list API failed.",
                            details={"cause": type(exc).__name__},
                        )
                    )
    except Exception as exc:
        _handle_error(exc, classify_error)
        panel_ok = False
        sources = sources.model_copy(update={"panel": "unavailable", "nodes": "unavailable", "users": "unavailable"})
        warnings.append(
            _system_warning(
                "MERIDIAN_PANEL_UNREACHABLE",
                "Cannot reach panel API -- node and user data may be stale",
                hint="Check panel connectivity and run meridian doctor.",
                details={"cause": type(exc).__name__},
            )
        )

    relay_health = check_relays(topology.relays)
    return FleetStatusServiceResult(
        status=build_fleet_status(
            topology,
            panel_healthy=panel_ok,
            api_nodes=api_nodes,
            api_users=api_users,
            relay_health=relay_health,
            sources=sources,
        ),
        warnings=warnings,
    )
