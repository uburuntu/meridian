"""Declarative plan command — show what would change without changing anything.

Reads cluster.yml v2 desired state, fetches actual state from the panel
API, and prints a terraform-style diff. Exit codes:
  0 = already converged (no changes needed)
  2 = changes pending
"""

from __future__ import annotations

import json
import sys

import typer

from meridian.cluster import ClusterConfig
from meridian.console import err_console, fail, info
from meridian.reconciler import compute_plan
from meridian.reconciler.display import print_plan
from meridian.reconciler.state import build_actual_state, build_desired_state


def _emit_json(plan, exit_code: int) -> None:
    """Serialize a Plan to stdout as JSON for CI consumption.

    Schema is intentionally flat and dataclass-friendly so a downstream
    `jq` pipeline can do `.actions[] | select(.kind == "remove_client")`.
    Writes to stdout (not stderr) so the JSON is the entire program output
    in --json mode.
    """
    payload = {
        "converged": plan.is_empty,
        "summary": plan.summary(),
        "exit_code": exit_code,
        "actions": [
            {
                "kind": a.kind.value,
                "target": a.target,
                "detail": a.detail,
                "destructive": a.destructive,
                "from_extras": a.from_extras,
                "symbol": a.symbol,
            }
            for a in plan.actions
        ],
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    sys.stdout.flush()


def run(json_output: bool = False) -> None:
    """Show what meridian apply would do, without changing anything."""
    cluster = ClusterConfig.load()

    has_desired = (
        cluster.desired_nodes is not None or cluster.desired_clients is not None or cluster.desired_relays is not None
    )
    has_sub_page = cluster.subscription_page and (
        cluster.subscription_page.enabled or cluster.subscription_page._extra.get("deployed", False)
    )
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
    from meridian.ssh import ServerConnection

    try:
        # SSH connection to panel host for live subscription page check
        panel_conn = None
        if cluster.panel.server_ip:
            panel_conn = ServerConnection(cluster.panel.server_ip, cluster.panel.ssh_user, port=cluster.panel.ssh_port)

        with MeridianPanel(cluster.panel.url, cluster.panel.api_token) as panel:
            desired = build_desired_state(cluster)
            actual = build_actual_state(cluster, panel, panel_conn=panel_conn)
    except RemnawaveError as e:
        fail(f"Cannot reach panel: {e}", hint_type="system")

    from meridian.operations import load_applied_snapshot

    plan = compute_plan(
        desired,
        actual,
        applied_clients=load_applied_snapshot(cluster, "desired_clients_applied"),
        applied_node_hosts=load_applied_snapshot(cluster, "desired_nodes_applied"),
        applied_relay_hosts=load_applied_snapshot(cluster, "desired_relays_applied"),
    )
    exit_code = 0 if plan.is_empty else 2

    if json_output:
        _emit_json(plan, exit_code=exit_code)
    else:
        print_plan(plan, console=err_console)

    raise typer.Exit(exit_code)
