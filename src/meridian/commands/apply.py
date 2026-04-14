"""Declarative apply command — converge actual state to desired state.

Reads cluster.yml v2, computes a plan, confirms with the user, and
executes. Reuses existing provisioning code via the reconciler executor.
"""

from __future__ import annotations

import typer

from meridian.cluster import ClusterConfig
from meridian.console import confirm, err_console, fail, info, ok, warn
from meridian.reconciler import PlanActionKind, compute_plan
from meridian.reconciler.diff import PlanAction
from meridian.reconciler.display import print_plan
from meridian.reconciler.executor import execute_plan
from meridian.reconciler.state import build_actual_state, build_desired_state


def _handle_add_node(action: PlanAction, panel: object, cluster: object) -> None:
    """Provision and register a new node."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import add_node
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    # Find the desired node spec to get SSH/domain/sni params
    desired = next((n for n in cluster.desired_nodes if n.host == action.target), None)
    add_node(
        cluster,
        panel,
        ip=action.target,
        ssh_user=desired.ssh_user if desired else "root",
        ssh_port=desired.ssh_port if desired else 22,
        name=desired.name if desired else "",
        domain=desired.domain if desired else "",
        sni=desired.sni if desired else "",
        warp=desired.warp if desired else False,
    )


def _handle_update_node(action: PlanAction, panel: object, cluster: object) -> None:
    """Redeploy a node with updated configuration."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import update_node
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    desired = next((n for n in cluster.desired_nodes if n.host == action.target), None)
    update_node(
        cluster,
        panel,
        ip=action.target,
        sni=desired.sni if desired else "",
        domain=desired.domain if desired else "",
        warp=desired.warp if desired else False,
    )


def _handle_remove_node(action: PlanAction, panel: object, cluster: object) -> None:
    """Deregister and remove a node."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import remove_node
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)
    remove_node(cluster, panel, node_ip=action.target, force=True)


def _handle_add_relay(action: PlanAction, panel: object, cluster: object) -> None:
    """Provision and register a new relay."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import add_relay
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    desired = next((r for r in cluster.desired_relays if r.host == action.target), None)
    add_relay(
        cluster,
        panel,
        relay_ip=action.target,
        exit_node_ip=desired.exit_node if desired else "",
        ssh_user=desired.ssh_user if desired else "root",
        ssh_port=desired.ssh_port if desired else 22,
        name=desired.name if desired else "",
    )


def _handle_remove_relay(action: PlanAction, panel: object, cluster: object) -> None:
    """Remove a relay."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import remove_relay
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)
    remove_relay(cluster, panel, relay_ip=action.target)


def _handle_add_client(action: PlanAction, panel: object, cluster: object) -> None:
    """Create a client via the panel API."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import add_client
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)
    add_client(cluster, panel, name=action.target)


def _handle_remove_client(action: PlanAction, panel: object, cluster: object) -> None:
    """Delete a client via the panel API."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import remove_client
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)
    remove_client(cluster, panel, name=action.target)


def _handle_add_subscription_page(action: PlanAction, panel: object, cluster: object) -> None:
    """Deploy the subscription page container."""
    from meridian.cluster import ClusterConfig
    from meridian.provision.remnawave_panel import configure_subscription_page
    from meridian.remnawave import MeridianPanel
    from meridian.ssh import ServerConnection

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    if not cluster.panel.server_ip:
        raise RuntimeError("Panel server IP not set in cluster config")

    conn = ServerConnection(cluster.panel.server_ip, cluster.panel.ssh_user, port=cluster.panel.ssh_port)
    if not configure_subscription_page(conn, cluster.panel.api_token):
        raise RuntimeError("Failed to configure subscription page")

    cluster.subscription_page.enabled = True
    cluster.subscription_page._extra["deployed"] = True
    cluster.save()


def _handle_remove_subscription_page(action: PlanAction, panel: object, cluster: object) -> None:
    """Stop the subscription page container."""
    from meridian.cluster import ClusterConfig
    from meridian.config import REMNAWAVE_PANEL_DIR
    from meridian.ssh import ServerConnection

    assert isinstance(cluster, ClusterConfig)

    if not cluster.panel.server_ip:
        raise RuntimeError("Panel server IP not set in cluster config")

    conn = ServerConnection(cluster.panel.server_ip, cluster.panel.ssh_user, port=cluster.panel.ssh_port)
    import shlex

    q_dir = shlex.quote(REMNAWAVE_PANEL_DIR)
    result = conn.run(f"cd {q_dir} && docker compose stop remnawave-subscription-page", timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to stop subscription page: {result.stderr.strip()[:200]}")

    cluster.subscription_page.enabled = False
    cluster.subscription_page._extra["deployed"] = False
    cluster.save()


def run(
    yes: bool = False,
    parallel: int = 4,
) -> None:
    """Converge actual state to desired state declared in cluster.yml."""
    cluster = ClusterConfig.load()

    has_desired = (
        cluster.desired_nodes is not None or cluster.desired_clients is not None or cluster.desired_relays is not None
    )
    has_sub_page = cluster.subscription_page and cluster.subscription_page.enabled
    if not has_desired and not has_sub_page:
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
                PlanActionKind.ADD_NODE: _handle_add_node,
                PlanActionKind.UPDATE_NODE: _handle_update_node,
                PlanActionKind.REMOVE_NODE: _handle_remove_node,
                PlanActionKind.ADD_RELAY: _handle_add_relay,
                PlanActionKind.REMOVE_RELAY: _handle_remove_relay,
                PlanActionKind.ADD_CLIENT: _handle_add_client,
                PlanActionKind.REMOVE_CLIENT: _handle_remove_client,
                PlanActionKind.ADD_SUBSCRIPTION_PAGE: _handle_add_subscription_page,
                PlanActionKind.REMOVE_SUBSCRIPTION_PAGE: _handle_remove_subscription_page,
            }

            result = execute_plan(plan, panel=panel, cluster=cluster, callbacks=callbacks, max_parallel=parallel)

            cluster.save()

            if result.all_succeeded:
                ok(result.summary())
            else:
                for failed_action in result.failed:
                    warn(f"Failed: {failed_action.action.detail} — {failed_action.error}")
                fail(result.summary(), hint_type="system")

    except RemnawaveError as e:
        fail(f"Panel API error: {e}", hint_type="system")
