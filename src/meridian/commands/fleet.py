"""Fleet status -- overview of all nodes, relays, and users.

Single command that shows the health of the entire Meridian cluster
at a glance: panel connectivity, node status, relay reachability, user count.
"""

from __future__ import annotations

import socket
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from meridian.adapters.cluster import topology_from_cluster
from meridian.commands._helpers import format_traffic, load_cluster, make_panel
from meridian.console import err_console, error_context, fail, is_json_mode, warn
from meridian.core.fleet import (
    ApiNodeLike,
    ApiUserLike,
    FleetSources,
    FleetStatus,
    FleetTopology,
    SourceAvailability,
    TopologyRelay,
    build_fleet_inventory,
    build_fleet_status,
)
from meridian.core.models import MeridianError, Summary
from meridian.core.output import OperationContext, envelope
from meridian.remnawave import RemnawaveAuthError, RemnawaveError
from meridian.renderers import emit_json


def _check_relay_health(ip: str, port: int, timeout: float = 3.0) -> bool:
    """TCP connect check to verify relay is reachable."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _check_relays_health(
    relays: list[TopologyRelay], *, timeout: float = 3.0, max_workers: int = 8
) -> dict[tuple[str, int], bool]:
    """Check relay health concurrently with a bounded worker pool."""
    if not relays:
        return {}
    results: dict[tuple[str, int], bool] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(relays))) as executor:
        futures = {
            executor.submit(_check_relay_health, relay.ip, relay.port, timeout): (relay.ip, relay.port)
            for relay in relays
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _warning(code: str, message: str, *, hint: str = "", details: dict[str, object] | None = None) -> MeridianError:
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


def _add_warning(warnings: list[MeridianError], warning: MeridianError) -> None:
    warnings.append(warning)
    if not is_json_mode():
        warn(warning.message)


# -- Fleet Inventory --


def run_inventory() -> None:
    """Show the configured fleet inventory without exposing secrets."""
    operation = OperationContext()
    with error_context("fleet.inventory", timer=operation.timer):
        _run_inventory(operation=operation)


def _run_inventory(*, operation: OperationContext) -> None:
    """Implementation for inventory with command metadata already attached."""
    cluster = load_cluster()
    topology = topology_from_cluster(cluster)
    panel_ok = False
    api_nodes: Sequence[ApiNodeLike] = []
    warnings: list[MeridianError] = []
    sources = FleetSources(panel="unknown", nodes="not_requested", users="not_requested", relays="not_requested")

    try:
        panel = make_panel(cluster)
        with panel:
            panel_ok = panel.ping()
            sources = sources.model_copy(update={"panel": "available" if panel_ok else "unavailable"})
            if not panel_ok:
                _add_warning(
                    warnings,
                    _warning(
                        "MERIDIAN_PANEL_UNREACHABLE",
                        "Cannot reach panel API; live inventory status is unavailable",
                        hint="Check panel connectivity and run meridian doctor.",
                    ),
                )
            if panel_ok:
                try:
                    api_nodes = panel.list_nodes()
                    sources = sources.model_copy(update={"nodes": "available"})
                except RemnawaveAuthError as exc:
                    fail(str(exc), hint=exc.hint, hint_type=exc.hint_type)
                except RemnawaveError as exc:
                    sources = sources.model_copy(update={"nodes": "unavailable"})
                    _add_warning(
                        warnings,
                        _warning(
                            "MERIDIAN_PANEL_NODES_UNAVAILABLE",
                            "Could not fetch node status from panel",
                            hint="Panel is reachable, but the node list API failed.",
                            details={"cause": type(exc).__name__},
                        ),
                    )
            else:
                sources = sources.model_copy(update={"nodes": "unavailable"})
    except RemnawaveAuthError as exc:
        fail(str(exc), hint=exc.hint, hint_type=exc.hint_type)
    except RemnawaveError as exc:
        panel_ok = False
        sources = sources.model_copy(update={"panel": "unavailable", "nodes": "unavailable"})
        _add_warning(
            warnings,
            _warning(
                "MERIDIAN_PANEL_UNREACHABLE",
                "Cannot reach panel API; live inventory status is unavailable",
                hint="Check panel connectivity and run meridian doctor.",
                details={"cause": type(exc).__name__},
            ),
        )

    inventory = build_fleet_inventory(topology, panel_healthy=panel_ok, api_nodes=api_nodes, sources=sources)
    data = inventory.to_data()

    if is_json_mode():
        emit_json(
            envelope(
                command="fleet.inventory",
                data=data,
                summary=Summary(
                    text=inventory.summary.text,
                    changed=inventory.summary.pending > 0,
                    counts={
                        "nodes": inventory.summary.nodes,
                        "relays": inventory.summary.relays,
                        "pending": inventory.summary.pending,
                    },
                ),
                status="ok",
                warnings=warnings,
                timer=operation.timer,
            )
        )
        return

    err_console.print()
    status = "[green]healthy[/green]" if panel_ok else "[red]UNREACHABLE[/red]"
    err_console.print(f"  [bold]Panel[/bold]   {inventory.panel.url}  {status}")
    if cluster.panel.server_ip:
        err_console.print(
            f"            SSH {cluster.panel.ssh_user}@{cluster.panel.server_ip}:{cluster.panel.ssh_port}"
        )

    err_console.print()
    err_console.print("  [bold]Nodes[/bold]")
    if not inventory.nodes:
        err_console.print("    [dim]none[/dim]")
    for display_node in inventory.nodes:
        desired = (
            "" if display_node.desired is None else "  desired" if display_node.desired else "  [yellow]extra[/yellow]"
        )
        domain = f"  domain={display_node.domain}" if display_node.domain else ""
        err_console.print(
            f"    {display_node.ip}  {display_node.name or '-'}  {display_node.role}  "
            f"{display_node.panel_status}{domain}{desired}"
        )

    err_console.print()
    err_console.print("  [bold]Relays[/bold]")
    if not inventory.relays:
        err_console.print("    [dim]none[/dim]")
    for display_relay in inventory.relays:
        target = display_relay.exit_node_name or display_relay.exit_node_ip
        desired = (
            ""
            if display_relay.desired is None
            else "  desired"
            if display_relay.desired
            else "  [yellow]extra[/yellow]"
        )
        err_console.print(
            f"    {display_relay.ip}  {display_relay.name or '-'}  :{display_relay.port} -> {target}{desired}"
        )

    if inventory.summary.desired_nodes or inventory.summary.desired_relays:
        err_console.print()
        err_console.print(
            "  [bold]Desired[/bold] "
            f"{inventory.summary.desired_nodes} node(s), {inventory.summary.desired_relays} relay(s); "
            f"{inventory.summary.pending} pending"
        )
    err_console.print()


# -- Fleet Status --


def _render_status(status: FleetStatus) -> None:
    """Render fleet status for humans from the typed core result."""
    err_console.print()
    panel_state = "[green]healthy[/green]" if status.panel.healthy else "[red]UNREACHABLE[/red]"
    err_console.print(f"  [bold]Panel[/bold]   {status.panel.url} {panel_state}")

    if status.nodes:
        err_console.print()
        err_console.print("  [bold]Nodes[/bold]")

        for node in status.nodes:
            label = node.name or node.ip
            role = "  [dim](panel)[/dim]" if node.is_panel_host else ""

            if node.status == "connected":
                xray = f"  Xray {node.xray_version}" if node.xray_version else ""
                traffic = f"  {format_traffic(node.traffic_bytes)}" if node.traffic_bytes else ""
                err_console.print(f"    {node.ip}  {label}{role}  [green]connected[/green]{xray}{traffic}")
            elif node.status == "disabled":
                err_console.print(f"    {node.ip}  {label}{role}  [dim]disabled[/dim]")
            elif node.status == "disconnected":
                err_console.print(f"    {node.ip}  {label}{role}  [red]DISCONNECTED[/red]")
            else:
                err_console.print(f"    {node.ip}  {label}{role}  [dim]unknown[/dim]")

    if status.relays:
        err_console.print()
        err_console.print("  [bold]Relays[/bold]")

        for relay in status.relays:
            label = relay.name or relay.ip
            target_label = relay.exit_node_name or relay.exit_node_ip
            if relay.health == "healthy":
                relay_state = "[green]healthy[/green]"
            elif relay.health == "unhealthy":
                relay_state = "[red]UNREACHABLE[/red]"
            else:
                relay_state = "[dim]unknown[/dim]"

            err_console.print(f"    {relay.ip}  {label} -> {target_label}  relay: {relay_state}")

    if status.users:
        err_console.print()
        parts = [f"{status.summary.active_users} active"]
        if status.summary.disabled_users:
            parts.append(f"{status.summary.disabled_users} disabled")
        if status.summary.other_users:
            parts.append(f"{status.summary.other_users} other")
        err_console.print(f"  [bold]Users[/bold]   {', '.join(parts)}")

    err_console.print()


def run_status() -> None:
    """Show fleet health overview: panel, nodes, relays, users."""
    operation = OperationContext()
    with error_context("fleet.status", timer=operation.timer):
        _run_status(operation=operation)


def _run_status(*, operation: OperationContext) -> None:
    """Implementation for status with command metadata already attached."""
    cluster = load_cluster()
    topology = topology_from_cluster(cluster)
    panel = make_panel(cluster)
    panel_ok = False
    api_nodes: Sequence[ApiNodeLike] = []
    api_users: Sequence[ApiUserLike] = []
    warnings: list[MeridianError] = []
    relay_source: SourceAvailability = "available" if topology.relays else "not_requested"
    sources = FleetSources(panel="unknown", nodes="not_requested", users="not_requested", relays=relay_source)

    try:
        with panel:
            panel_ok = panel.ping()
            sources = sources.model_copy(update={"panel": "available" if panel_ok else "unavailable"})
            if not panel_ok:
                _add_warning(
                    warnings,
                    _warning(
                        "MERIDIAN_PANEL_UNREACHABLE",
                        "Cannot reach panel API -- node and user data may be stale",
                        hint="Check panel connectivity and run meridian doctor.",
                    ),
                )
                sources = sources.model_copy(update={"nodes": "unavailable", "users": "unavailable"})
                return _finish_status(
                    operation=operation,
                    topology=topology,
                    panel_ok=panel_ok,
                    api_nodes=api_nodes,
                    api_users=api_users,
                    warnings=warnings,
                    sources=sources,
                )

            try:
                api_nodes = panel.list_nodes()
                sources = sources.model_copy(update={"nodes": "available"})
            except RemnawaveAuthError as exc:
                fail(str(exc), hint=exc.hint, hint_type=exc.hint_type)
            except RemnawaveError as exc:
                sources = sources.model_copy(update={"nodes": "unavailable"})
                _add_warning(
                    warnings,
                    _warning(
                        "MERIDIAN_PANEL_NODES_UNAVAILABLE",
                        "Could not fetch node status from panel",
                        hint="Panel is reachable, but the node list API failed.",
                        details={"cause": type(exc).__name__},
                    ),
                )
            try:
                api_users = panel.list_users()
                sources = sources.model_copy(update={"users": "available"})
            except RemnawaveAuthError as exc:
                fail(str(exc), hint=exc.hint, hint_type=exc.hint_type)
            except RemnawaveError as exc:
                sources = sources.model_copy(update={"users": "unavailable"})
                _add_warning(
                    warnings,
                    _warning(
                        "MERIDIAN_PANEL_USERS_UNAVAILABLE",
                        "Could not fetch user status from panel",
                        hint="Panel is reachable, but the user list API failed.",
                        details={"cause": type(exc).__name__},
                    ),
                )
    except RemnawaveAuthError as exc:
        fail(str(exc), hint=exc.hint, hint_type=exc.hint_type)
    except RemnawaveError as exc:
        panel_ok = False
        sources = sources.model_copy(update={"panel": "unavailable", "nodes": "unavailable", "users": "unavailable"})
        _add_warning(
            warnings,
            _warning(
                "MERIDIAN_PANEL_UNREACHABLE",
                "Cannot reach panel API -- node and user data may be stale",
                hint="Check panel connectivity and run meridian doctor.",
                details={"cause": type(exc).__name__},
            ),
        )

    _finish_status(
        operation=operation,
        topology=topology,
        panel_ok=panel_ok,
        api_nodes=api_nodes,
        api_users=api_users,
        warnings=warnings,
        sources=sources,
    )


def _finish_status(
    *,
    operation: OperationContext,
    topology: FleetTopology,
    panel_ok: bool,
    api_nodes: Sequence[ApiNodeLike],
    api_users: Sequence[ApiUserLike],
    warnings: list[MeridianError],
    sources: FleetSources,
) -> None:
    """Build and render the final status result."""

    relay_health = _check_relays_health(topology.relays)
    status = build_fleet_status(
        topology,
        panel_healthy=panel_ok,
        api_nodes=api_nodes,
        api_users=api_users,
        relay_health=relay_health,
        sources=sources,
    )

    if is_json_mode():
        emit_json(
            envelope(
                command="fleet.status",
                data=status.to_data(),
                summary=Summary(
                    text=status.summary.text,
                    changed=False,
                    counts={
                        "nodes": status.summary.nodes,
                        "relays": status.summary.relays,
                        "users": status.summary.users,
                        "unhealthy_relays": status.summary.unhealthy_relays,
                        "disconnected_nodes": status.summary.disconnected_nodes,
                        "disabled_nodes": status.summary.disabled_nodes,
                        "unknown_nodes": status.summary.unknown_nodes,
                    },
                ),
                warnings=warnings,
                timer=operation.timer,
            )
        )
        return

    _render_status(status)
