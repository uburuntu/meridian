"""Declarative apply command — converge actual state to desired state.

Reads cluster.yml v2, computes a plan, confirms with the user, and
executes. Reuses existing provisioning code via the reconciler executor.
"""

from __future__ import annotations

import typer

from meridian.cluster import ClusterConfig
from meridian.console import confirm, err_console, fail, info, ok, warn
from meridian.reconciler import PlanActionKind, compute_plan
from meridian.reconciler.display import print_plan
from meridian.reconciler.executor import execute_plan
from meridian.reconciler.state import build_actual_state, build_desired_state


def _handle_add_client(action: object, panel: object, cluster: object) -> None:
    """Create a client via the panel API."""
    from meridian.reconciler.diff import PlanAction
    from meridian.remnawave import MeridianPanel

    assert isinstance(action, PlanAction)
    assert isinstance(panel, MeridianPanel)
    panel.create_user(action.target)


def _handle_remove_client(action: object, panel: object, cluster: object) -> None:
    """Delete a client via the panel API."""
    from meridian.reconciler.diff import PlanAction
    from meridian.remnawave import MeridianPanel

    assert isinstance(action, PlanAction)
    assert isinstance(panel, MeridianPanel)
    user = panel.get_user(action.target)
    if user and user.uuid:
        panel.delete_user(user.uuid)


def run(
    yes: bool = False,
    parallel: int = 4,
) -> None:
    """Converge actual state to desired state declared in cluster.yml."""
    cluster = ClusterConfig.load()

    if not cluster.desired_nodes and not cluster.desired_clients and not cluster.desired_relays:
        fail(
            "No desired state defined in cluster.yml",
            hint=("Add desired_nodes, desired_clients, or desired_relays to cluster.yml,\nthen run: meridian apply"),
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
            plan = compute_plan(desired, actual)

            if plan.is_empty:
                ok("No changes needed — infrastructure is up to date.")
                raise typer.Exit(0)

            print_plan(plan, console=err_console)

            if plan.has_destructive and not yes:
                if not confirm("Plan includes destructive actions. Apply?"):
                    raise typer.Exit(1)
            elif not yes:
                if not confirm("Apply this plan?"):
                    raise typer.Exit(1)

            info("Applying plan...")
            callbacks = {
                PlanActionKind.ADD_CLIENT: _handle_add_client,
                PlanActionKind.REMOVE_CLIENT: _handle_remove_client,
                # Node and relay handlers will be wired when the provisioning
                # code is refactored into callable units. For now, plan shows
                # what would change; apply handles clients.
            }

            result = execute_plan(plan, panel=panel, cluster=cluster, callbacks=callbacks)

            if result.all_succeeded:
                ok(result.summary())
            else:
                for failed in result.failed:
                    warn(f"Failed: {failed.action.detail} — {failed.error}")
                warn(result.summary())

            cluster.save()

    except RemnawaveError as e:
        fail(f"Panel API error: {e}", hint_type="system")
