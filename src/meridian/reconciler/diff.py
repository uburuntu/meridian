"""Pure diff engine — compare desired and actual state to produce a plan.

``compute_plan()`` is a pure function: no I/O, no side effects, fully
unit-testable. It takes two state snapshots and returns a list of typed
actions needed to converge actual → desired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from meridian.reconciler.state import ActualState, DesiredState


class PlanActionKind(str, Enum):
    """Types of reconciliation actions."""

    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    ADD_CLIENT = "add_client"
    REMOVE_CLIENT = "remove_client"
    ADD_RELAY = "add_relay"
    REMOVE_RELAY = "remove_relay"
    ADD_SUBSCRIPTION_PAGE = "add_subscription_page"
    REMOVE_SUBSCRIPTION_PAGE = "remove_subscription_page"


@dataclass
class PlanAction:
    """A single reconciliation action."""

    kind: PlanActionKind
    target: str  # identifier (IP, username, name)
    detail: str = ""  # human-readable description
    destructive: bool = False  # requires --yes confirmation

    @property
    def symbol(self) -> str:
        """Terraform-style symbol for display."""
        if self.kind.name.startswith("ADD"):
            return "+"
        if self.kind.name.startswith("REMOVE"):
            return "-"
        return "~"


@dataclass
class Plan:
    """A reconciliation plan — the diff between desired and actual state."""

    actions: list[PlanAction] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """No changes needed — already converged."""
        return len(self.actions) == 0

    @property
    def has_destructive(self) -> bool:
        """Plan contains destructive actions (removals)."""
        return any(a.destructive for a in self.actions)

    @property
    def adds(self) -> list[PlanAction]:
        return [a for a in self.actions if a.symbol == "+"]

    @property
    def removes(self) -> list[PlanAction]:
        return [a for a in self.actions if a.symbol == "-"]

    def summary(self) -> str:
        """One-line summary: "Plan: 2 to add, 1 to remove"."""
        add_count = len(self.adds)
        remove_count = len(self.removes)
        if self.is_empty:
            return "No changes. Infrastructure is up to date."
        parts = []
        if add_count:
            parts.append(f"{add_count} to add")
        if remove_count:
            parts.append(f"{remove_count} to remove")
        return f"Plan: {', '.join(parts)}."


def compute_plan(desired: DesiredState, actual: ActualState) -> Plan:
    """Compute the reconciliation plan.

    Compares desired state with actual state and returns typed actions
    needed to converge. Pure function — no I/O.

    Action ordering: nodes → relays → clients → subscription page.
    This respects dependencies: nodes must exist before relays can
    forward to them, and hosts must exist before clients can connect.
    """
    actions: list[PlanAction] = []

    # --- Nodes ---
    actual_node_hosts = {n.host for n in actual.nodes}
    desired_node_hosts = {n.host for n in desired.nodes}

    for node in desired.nodes:
        if node.host not in actual_node_hosts:
            actions.append(
                PlanAction(
                    kind=PlanActionKind.ADD_NODE,
                    target=node.host,
                    detail=f"provision node {node.name or node.host}",
                )
            )

    for node in actual.nodes:
        if node.host not in desired_node_hosts:
            actions.append(
                PlanAction(
                    kind=PlanActionKind.REMOVE_NODE,
                    target=node.host,
                    detail=f"deregister node {node.name or node.host}",
                    destructive=True,
                )
            )

    # --- Relays ---
    actual_relay_hosts = {r.host for r in actual.relays}
    desired_relay_hosts = {r.host for r in desired.relays}

    for relay in desired.relays:
        if relay.host not in actual_relay_hosts:
            actions.append(
                PlanAction(
                    kind=PlanActionKind.ADD_RELAY,
                    target=relay.host,
                    detail=f"deploy relay {relay.name or relay.host} → {relay.exit_node}",
                )
            )

    for relay in actual.relays:
        if relay.host not in desired_relay_hosts:
            actions.append(
                PlanAction(
                    kind=PlanActionKind.REMOVE_RELAY,
                    target=relay.host,
                    detail=f"remove relay {relay.name or relay.host}",
                    destructive=True,
                )
            )

    # --- Clients ---
    actual_clients = set(actual.clients)
    desired_clients = set(desired.clients)

    for client in sorted(desired_clients - actual_clients):
        actions.append(
            PlanAction(
                kind=PlanActionKind.ADD_CLIENT,
                target=client,
                detail=f"create client {client}",
            )
        )

    for client in sorted(actual_clients - desired_clients):
        actions.append(
            PlanAction(
                kind=PlanActionKind.REMOVE_CLIENT,
                target=client,
                detail=f"delete client {client}",
                destructive=True,
            )
        )

    # --- Subscription page ---
    if desired.subscription_page_enabled and not actual.subscription_page_running:
        actions.append(
            PlanAction(
                kind=PlanActionKind.ADD_SUBSCRIPTION_PAGE,
                target="subscription-page",
                detail="deploy subscription page container",
            )
        )
    elif not desired.subscription_page_enabled and actual.subscription_page_running:
        actions.append(
            PlanAction(
                kind=PlanActionKind.REMOVE_SUBSCRIPTION_PAGE,
                target="subscription-page",
                detail="remove subscription page container",
                destructive=True,
            )
        )

    return Plan(actions=actions)
