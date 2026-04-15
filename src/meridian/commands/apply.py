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


def _looks_like_ip(s: str) -> bool:
    """Cheap guard for the UPDATE_RELAY exit-node resolution path.

    Used only to distinguish "user wrote an IP literally" from "user wrote a
    node name that doesn't exist in the cluster". Strict IP validation is not
    required — we just need to know we should not refuse.
    """
    parts = s.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def _handle_add_node(action: PlanAction, panel: object, cluster: object) -> None:
    """Provision and register a new node."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import add_node
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    # Find the desired node spec to get SSH/domain/sni params
    desired = next((n for n in (cluster.desired_nodes or []) if n.host == action.target), None)
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

    desired = next((n for n in (cluster.desired_nodes or []) if n.host == action.target), None)
    update_node(
        cluster,
        panel,
        ip=action.target,
        name=desired.name if desired and desired.name else None,
        sni=desired.sni if desired else None,
        domain=desired.domain if desired else None,
        warp=desired.warp if desired else False,
    )


def _handle_remove_node(action: PlanAction, panel: object, cluster: object) -> None:
    """Deregister and remove a node."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import remove_node
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)
    remove_node(cluster, panel, node_ip=action.target)


def _handle_add_relay(action: PlanAction, panel: object, cluster: object) -> None:
    """Provision and register a new relay."""
    from meridian.cluster import ClusterConfig
    from meridian.operations import add_relay
    from meridian.remnawave import MeridianPanel

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    desired = next((r for r in (cluster.desired_relays or []) if r.host == action.target), None)
    # Resolve exit_node name → IP (desired.exit_node can be a name or IP)
    exit_node_value = desired.exit_node if desired else ""
    if exit_node_value:
        exit_node_entry = cluster.find_node(exit_node_value)
        if exit_node_entry:
            exit_node_value = exit_node_entry.ip
    add_relay(
        cluster,
        panel,
        relay_ip=action.target,
        exit_node_ip=exit_node_value,
        ssh_user=desired.ssh_user if desired else "root",
        ssh_port=desired.ssh_port if desired else 22,
        name=desired.name or desired.host if desired else "",
        sni=desired.sni if desired else "",
    )


def _handle_update_relay(action: PlanAction, panel: object, cluster: object) -> None:
    """Update a relay by removing the old config and re-provisioning with the new one.

    Failure semantics: this action is destructive — once the old relay is
    removed, traffic for clients pointing to it stops. To keep the window as
    short as possible (and avoid leaving the cluster with no relay at all when
    the new config is unreachable), we preflight the new exit node + new SSH
    target before we touch the existing relay. If preflight fails we leave
    the old relay alone and surface a RuntimeError.

    NOTE: this is best-effort safety. A successful preflight does not
    guarantee that the subsequent provisioning will succeed — but it catches
    the common cases (panel cannot reach new exit node, SSH cannot reach new
    relay host) before we do any irreversible work.
    """
    from meridian.cluster import ClusterConfig
    from meridian.operations import add_relay, remove_relay
    from meridian.remnawave import MeridianPanel
    from meridian.ssh import ServerConnection

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    desired = next(
        (r for r in (cluster.desired_relays or []) if r.host == action.target),
        None,
    )
    if desired is None:
        # Nothing to update to — the diff should not have produced this case,
        # but be defensive and avoid wiping the existing relay for nothing.
        raise RuntimeError(
            f"UPDATE_RELAY for {action.target} but no matching desired relay in cluster.yml — refusing to delete"
        )

    # Resolve exit_node name → IP. If desired.exit_node is already an IP
    # (no matching node entry by that name), leave it as-is — but if it
    # looks like a name and there is no such node, refuse to proceed.
    exit_node_value = desired.exit_node or ""
    resolved = False
    if exit_node_value:
        exit_node_entry = cluster.find_node(exit_node_value)
        if exit_node_entry:
            exit_node_value = exit_node_entry.ip
            resolved = True
        elif _looks_like_ip(exit_node_value):
            resolved = True

    if not exit_node_value or not resolved:
        raise RuntimeError(
            f"UPDATE_RELAY for {action.target}: desired exit_node "
            f"'{desired.exit_node}' could not be resolved to an IP — refusing to delete old relay"
        )

    # --- Preflight: SSH connectivity to the new relay host ---
    # If we can't even open a session to the new target, there is no point
    # tearing down the old relay first.
    try:
        ssh_check = ServerConnection(action.target, desired.ssh_user, port=desired.ssh_port)
        result = ssh_check.run("true", timeout=15)
        if result.returncode != 0:
            raise RuntimeError(
                f"SSH preflight to {desired.ssh_user}@{action.target}:{desired.ssh_port} "
                f"returned exit {result.returncode} — refusing to remove the running relay"
            )
    except Exception as e:
        raise RuntimeError(f"UPDATE_RELAY preflight failed for {action.target}: {e}. Old relay left intact.") from e

    # Preflight passed — proceed with the destructive swap.
    remove_relay(cluster, panel, relay_ip=action.target)
    add_relay(
        cluster,
        panel,
        relay_ip=action.target,
        exit_node_ip=exit_node_value,
        ssh_user=desired.ssh_user,
        ssh_port=desired.ssh_port,
        name=desired.name or desired.host,
        sni=desired.sni,
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
    """Deploy the subscription page container.

    Handles both fresh deploys (container not in compose) and restarts
    (container exists but stopped). Regenerates docker-compose.yml if the
    subscription page service is missing, then configures with API token.
    """
    import shlex

    from meridian.cluster import ClusterConfig
    from meridian.config import (
        REMNAWAVE_BACKEND_IMAGE,
        REMNAWAVE_PANEL_DIR,
        REMNAWAVE_PANEL_PORT,
        REMNAWAVE_SUBSCRIPTION_PAGE_IMAGE,
        REMNAWAVE_SUBSCRIPTION_PAGE_PORT,
    )
    from meridian.provision.remnawave_panel import (
        _render_panel_compose,
        configure_subscription_page,
    )
    from meridian.remnawave import MeridianPanel
    from meridian.ssh import ServerConnection

    assert isinstance(panel, MeridianPanel)
    assert isinstance(cluster, ClusterConfig)

    if not cluster.panel.server_ip:
        raise RuntimeError("Panel server IP not set in cluster config")

    conn = ServerConnection(cluster.panel.server_ip, cluster.panel.ssh_user, port=cluster.panel.ssh_port)

    # Check if subscription page container exists in docker-compose
    q_dir = shlex.quote(REMNAWAVE_PANEL_DIR)
    check = conn.run(
        f"cd {q_dir} && docker compose config --services 2>/dev/null | grep -q subscription",
        timeout=15,
    )
    if check.returncode != 0:
        # Container not in compose — regenerate compose file, create placeholder
        # .env.subscription (required by compose), then bring up
        compose = _render_panel_compose(
            image=REMNAWAVE_BACKEND_IMAGE,
            panel_port=REMNAWAVE_PANEL_PORT,
            subscription_page_image=REMNAWAVE_SUBSCRIPTION_PAGE_IMAGE,
            subscription_page_host_port=REMNAWAVE_SUBSCRIPTION_PAGE_PORT,
        )
        compose_path = f"{REMNAWAVE_PANEL_DIR}/docker-compose.yml"
        write_cmd = f"cat > {shlex.quote(compose_path)} << 'MERIDIAN_EOF'\n{compose}MERIDIAN_EOF"
        result = conn.run(write_cmd, timeout=15)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to write docker-compose.yml: {result.stderr.strip()[:200]}")

        # Create placeholder .env.subscription so docker compose up doesn't fail
        from meridian.provision.remnawave_panel import _render_subscription_env

        sub_env = _render_subscription_env()
        sub_env_path = f"{REMNAWAVE_PANEL_DIR}/.env.subscription"
        write_env = f"cat > {shlex.quote(sub_env_path)} << 'MERIDIAN_EOF'\n{sub_env}MERIDIAN_EOF"
        conn.run(write_env, timeout=15)
        conn.run(f"chmod 600 {shlex.quote(sub_env_path)}", timeout=15)

        result = conn.run(f"cd {q_dir} && docker compose up -d", timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start containers: {result.stderr.strip()[:200]}")
    else:
        # Service exists in compose but may be stopped (e.g. from a prior
        # REMOVE_SUBSCRIPTION_PAGE that ran `docker compose stop`). Bring it
        # up — `docker compose up -d <service>` is idempotent and a no-op
        # when the container is already running.
        result = conn.run(
            f"cd {q_dir} && docker compose up -d remnawave-subscription-page",
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start subscription page container: {result.stderr.strip()[:200]}")

    if not configure_subscription_page(conn, cluster.panel.api_token):
        raise RuntimeError("Failed to configure subscription page")

    # Ensure nginx has a proxy route for the subscription page.
    # Generate a random path if none exists (same approach as provisioner).
    sub_path = cluster.subscription_page.path if cluster.subscription_page else ""
    if not sub_path:
        import secrets

        sub_path = secrets.token_hex(8)

    # Inject subscription page nginx location into the existing server block.
    # Check if already configured, skip if so.
    from meridian.config import REMNAWAVE_SUBSCRIPTION_PAGE_PORT

    check_existing = conn.run(
        f"grep -q {shlex.quote(sub_path)} /etc/nginx/conf.d/meridian-http.conf 2>/dev/null",
        timeout=15,
    )
    if check_existing.returncode != 0:
        # The location block must go inside the server{} block in meridian-http.conf.
        # Insert before the "# Root:" comment (always present in rendered config).
        location_block = (
            f"        # --- Subscription Page (managed by meridian apply) ---\\n"
            f"        location /{sub_path}/ {{\\n"
            f"            proxy_pass http://127.0.0.1:{REMNAWAVE_SUBSCRIPTION_PAGE_PORT}/;\\n"
            f"            proxy_http_version 1.1;\\n"
            f"            proxy_set_header Host \\$host;\\n"
            f"            proxy_set_header X-Real-IP \\$remote_addr;\\n"
            f"            proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;\\n"
            f"            proxy_set_header X-Forwarded-Proto \\$scheme;\\n"
            f"        }}\\n"
        )
        conn.run(
            f"sed -i '/# Root:/i\\{location_block}' /etc/nginx/conf.d/meridian-http.conf",
            timeout=15,
        )
        result = conn.run("nginx -t 2>&1", timeout=15)
        if result.returncode == 0:
            conn.run("systemctl reload nginx", timeout=15)
        else:
            raise RuntimeError(f"nginx validation failed after adding subscription page: {result.stdout.strip()[:200]}")

    # Initialize subscription_page config if missing — apply was triggered by
    # a desired enable, so the config must exist after this handler runs.
    if cluster.subscription_page is None:
        from meridian.cluster import SubscriptionPageConfig

        cluster.subscription_page = SubscriptionPageConfig()
    cluster.subscription_page.enabled = True
    cluster.subscription_page.path = sub_path
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

    # Remove nginx location block for subscription page
    sub_path = cluster.subscription_page.path if cluster.subscription_page else ""
    if sub_path:
        conn.run(
            f"grep -q {shlex.quote(sub_path)} /etc/nginx/conf.d/meridian-http.conf 2>/dev/null"
            f" && sed -i '/Subscription Page/,/}}/d' /etc/nginx/conf.d/meridian-http.conf",
            timeout=15,
        )
        result = conn.run("nginx -t 2>&1", timeout=15)
        if result.returncode == 0:
            conn.run("systemctl reload nginx", timeout=15)

    if cluster.subscription_page is not None:
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
    has_sub_page = cluster.subscription_page and (
        cluster.subscription_page.enabled or cluster.subscription_page._extra.get("deployed", False)
    )
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
    from meridian.ssh import ServerConnection

    try:
        # SSH connection to panel host for live subscription page check
        panel_conn = None
        if cluster.panel.server_ip:
            panel_conn = ServerConnection(cluster.panel.server_ip, cluster.panel.ssh_user, port=cluster.panel.ssh_port)

        with MeridianPanel(cluster.panel.url, cluster.panel.api_token) as panel:
            desired = build_desired_state(cluster)
            actual = build_actual_state(cluster, panel, panel_conn=panel_conn)
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
                PlanActionKind.UPDATE_RELAY: _handle_update_relay,
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
