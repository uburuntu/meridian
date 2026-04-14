"""Declarative plan command — show what would change without changing anything.

Reads cluster.yml v2 desired state, fetches actual state from the panel
API, and prints a terraform-style diff. Exit codes:
  0 = already converged (no changes needed)
  2 = changes pending
"""

from __future__ import annotations

import typer

from meridian.cluster import ClusterConfig
from meridian.console import err_console, fail, info
from meridian.reconciler import compute_plan
from meridian.reconciler.display import print_plan
from meridian.reconciler.state import build_actual_state, build_desired_state


def run() -> None:
    """Show what meridian apply would do, without changing anything."""
    cluster = ClusterConfig.load()

    has_desired = cluster.desired_nodes or cluster.desired_clients or cluster.desired_relays
    has_sub_page = cluster.subscription_page and cluster.subscription_page.enabled
    if not has_desired and not has_sub_page:
        fail(
            "No desired state defined in cluster.yml",
            hint=("Add desired_nodes, desired_clients, or desired_relays to cluster.yml,\nthen run: meridian plan"),
            hint_type="user",
        )

    if not cluster.is_configured:
        fail(
            "No panel configured — deploy first with: meridian deploy <IP>",
            hint_type="user",
        )

    info("Fetching actual state from panel...")
    from meridian.remnawave import MeridianPanel, RemnawaveError

    try:
        with MeridianPanel(cluster.panel.url, cluster.panel.api_token) as panel:
            desired = build_desired_state(cluster)
            actual = build_actual_state(cluster, panel)
    except RemnawaveError as e:
        fail(f"Cannot reach panel: {e}", hint_type="system")

    plan = compute_plan(desired, actual)
    print_plan(plan, console=err_console)

    if plan.is_empty:
        raise typer.Exit(0)
    raise typer.Exit(2)
