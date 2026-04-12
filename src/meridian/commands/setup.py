"""Deploy proxy server — interactive wizard and provisioner execution.

Meridian 4.0: Remnawave panel + node architecture. The provisioner deploys
containers via SSH, then this module calls the Remnawave REST API directly
from the deployer's machine to configure users, profiles, and hosts.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import shlex
import time

from meridian.cluster import (
    BrandingConfig,
    ClusterConfig,
    InboundRef,
    NodeEntry,
    PanelConfig,
    ProtocolKey,
)
from meridian.commands.resolve import (
    ResolvedServer,
    detect_public_ip,
    ensure_server_connection,
    is_local_keyword,
    resolve_server,
)
from meridian.config import (
    DEFAULT_SNI,
    REMNAWAVE_NODE_API_PORT,
    SERVERS_FILE,
    is_ip,
)
from meridian.console import choose, confirm, err_console, fail, info, line, ok, prompt, warn
from meridian.remnawave import MeridianPanel, RemnawaveError
from meridian.servers import ServerEntry, ServerRegistry
from meridian.ssh import ServerConnection

# ---------------------------------------------------------------------------
# Entry point (called from cli.py as `run`)
# ---------------------------------------------------------------------------


def run(
    ip: str = "",
    domain: str = "",
    sni: str = "",
    client_name: str = "",
    user: str = "root",
    yes: bool = False,
    harden: bool = True,
    requested_server: str = "",
    *,
    server_name: str = "",
    icon: str = "",
    color: str = "",
    decoy: str = "",
    pq: bool = False,
    warp: bool = False,
    geo_block: bool = True,
    ssh_port: int = 22,
) -> None:
    """Deploy a VLESS+Reality proxy server (Remnawave architecture)."""
    # --decoy is deprecated (403/404 is now always the default).
    # Accept silently for backwards compatibility but don't use it.

    registry = ServerRegistry(SERVERS_FILE)
    server_ip = ip
    ssh_user = user

    # --server flag: resolve from registry (or 'local' keyword)
    if requested_server:
        if server_ip:
            fail(
                "Use either the IP address or --server, not both.\n"
                "  Example: meridian deploy 1.2.3.4  OR  meridian deploy --server mybox",
                hint_type="user",
            )
        if is_local_keyword(requested_server):
            server_ip = requested_server
        else:
            entry = registry.find(requested_server)
            if not entry:
                if is_ip(requested_server):
                    server_ip = requested_server
                else:
                    fail(
                        f"Server '{requested_server}' not found",
                        hint="See registered servers: meridian server list",
                        hint_type="user",
                    )
            else:
                server_ip = entry.host
                if user == "root" and entry.user:
                    ssh_user = entry.user

    # Interactive wizard if no IP given
    if not server_ip:
        wizard_result = _interactive_wizard(
            sni=sni,
            domain=domain,
            harden=harden,
            yes=yes,
            client_name=client_name,
            server_name=server_name,
            icon=icon,
            color=color,
            pq=pq,
            warp=warp,
            geo_block=geo_block,
        )
        server_ip, ssh_user, sni, domain, harden = wizard_result[:5]
        client_name, server_name, icon, color, pq, warp, geo_block = wizard_result[5:]

    # Validate IP (skip for 'local' keyword -- resolve_server handles it)
    if not is_local_keyword(server_ip) and not is_ip(server_ip):
        fail(
            f"Invalid IP address: {server_ip}",
            hint="Enter a valid IP address (e.g. meridian deploy 123.45.67.89)",
            hint_type="user",
        )

    # Resolve and prepare SSH connection
    resolved = resolve_server(
        registry,
        explicit_ip=server_ip,
        user=ssh_user,
        port=ssh_port,
    )
    resolved = ensure_server_connection(resolved)
    _check_ports(resolved.conn, resolved.ip, yes)

    # Validate client name
    if client_name and not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", client_name):
        fail(
            f"Client name '{client_name}' is invalid",
            hint="Use letters, numbers, hyphens, and underscores.",
            hint_type="user",
        )
    if not client_name:
        client_name = "default"

    # Load existing cluster config
    cluster = ClusterConfig.load()

    # Determine deployment mode
    existing_node = cluster.find_node(resolved.ip)
    is_first_deploy = not cluster.is_configured
    is_redeploy = existing_node is not None
    if is_first_deploy:
        info("First deployment -- will set up panel + proxy node")
    elif is_redeploy:
        info(f"Redeploying existing node at {resolved.ip}")
    else:
        info(f"Adding new node at {resolved.ip} to existing cluster")

    # Compute port layout
    ip_hash = int(hashlib.sha256(resolved.ip.encode()).hexdigest()[:8], 16)
    xhttp_port = 30000 + (ip_hash % 10000)
    # nginx always runs in 4.0 (panel reverse proxy + connection pages),
    # so Reality must use an internal port, never 443 directly
    reality_port = 10000 + ip_hash % 1000
    wss_port = 20000 + (ip_hash % 10000)

    # Generate or reuse secret_path for panel nginx reverse proxy
    if is_redeploy and cluster.panel.secret_path:
        secret_path = cluster.panel.secret_path
    elif is_first_deploy:
        secret_path = secrets.token_hex(12)
    else:
        secret_path = cluster.panel.secret_path  # existing cluster

    # Generate or reuse xhttp/ws paths (persist across redeploys)
    if existing_node and existing_node.xhttp_path:
        xhttp_path = existing_node.xhttp_path
    else:
        xhttp_path = secrets.token_hex(8)
    if existing_node and existing_node.ws_path:
        ws_path = existing_node.ws_path
    else:
        ws_path = secrets.token_hex(8)

    # Build and run provisioner pipeline
    _run_provisioner(
        resolved=resolved,
        cluster=cluster,
        domain=domain,
        sni=sni,
        harden=harden,
        is_panel_host=is_first_deploy,
        secret_path=secret_path,
        xhttp_port=xhttp_port,
        reality_port=reality_port,
        wss_port=wss_port,
        pq=pq,
        warp=warp,
        geo_block=geo_block,
        xhttp_path=xhttp_path,
        ws_path=ws_path,
    )

    # Post-provisioner: configure panel via REST API
    _configure_panel_and_node(
        resolved=resolved,
        cluster=cluster,
        domain=domain,
        sni=sni or DEFAULT_SNI,
        client_name=client_name,
        is_first_deploy=is_first_deploy,
        is_redeploy=is_redeploy,
        secret_path=secret_path,
        reality_port=reality_port,
        xhttp_port=xhttp_port,
        wss_port=wss_port,
        pq=pq,
        geo_block=geo_block,
        xhttp_path=xhttp_path,
        ws_path=ws_path,
    )

    # Save branding
    if server_name or icon or color:
        cluster.branding = BrandingConfig(
            server_name=server_name,
            icon=icon,
            color=color,
        )

    # Save cluster config
    cluster.save()
    ok("Cluster configuration saved")

    # Register server in legacy registry (for --server flag resolution)
    registry.add(ServerEntry(host=resolved.ip, user=resolved.user, port=getattr(resolved.conn, "port", 22)))

    # Success output
    redeploy_cmd = _build_redeploy_command(
        resolved,
        sni=sni,
        domain=domain,
        client_name=client_name,
        harden=harden,
        server_name=server_name,
        icon=icon,
        color=color,
        pq=pq,
        warp=warp,
        geo_block=geo_block,
    )
    _print_success(
        resolved=resolved,
        cluster=cluster,
        client_name=client_name,
        domain=domain,
        redeploy_cmd=redeploy_cmd,
    )

    # Offer relay setup
    _offer_relay(resolved, yes)


# ---------------------------------------------------------------------------
# Provisioner pipeline
# ---------------------------------------------------------------------------


def _run_provisioner(
    resolved: ResolvedServer,
    cluster: ClusterConfig,
    domain: str,
    sni: str,
    harden: bool,
    is_panel_host: bool,
    secret_path: str,
    xhttp_port: int,
    reality_port: int,
    wss_port: int,
    *,
    pq: bool = False,
    warp: bool = False,
    geo_block: bool = True,
    xhttp_path: str = "",
    ws_path: str = "",
) -> None:
    """Run the SSH-based provisioner pipeline (OS, Docker, containers)."""
    from meridian.provision import ProvisionContext, Provisioner, build_node_steps, build_setup_steps

    ctx = ProvisionContext(
        ip=resolved.ip,
        user=resolved.user,
        domain=domain,
        sni=sni or DEFAULT_SNI,
        xhttp_enabled=True,
        pq_encryption=pq,
        warp=warp,
        geo_block=geo_block,
        hosted_page=True,
        harden=harden,
        is_panel_host=is_panel_host,
    )
    ctx.xhttp_port = xhttp_port
    ctx.reality_port = reality_port
    ctx.wss_port = wss_port

    # Store cluster and secret path in context for provisioner steps
    ctx.cluster = cluster
    ctx["secret_path"] = secret_path
    # nginx needs these paths for reverse proxy and connection page locations
    ctx["web_base_path"] = secret_path
    ctx["info_page_path"] = cluster.panel.sub_path if cluster.panel.sub_path else secrets.token_hex(8)
    # Provide xhttp/ws paths — reuse saved paths on redeploy, generate fresh otherwise
    ctx["xhttp_path"] = xhttp_path or secrets.token_hex(8)
    ctx["ws_path"] = ws_path or secrets.token_hex(8)

    err_console.print()
    info(f"Configuring server at {ctx.ip}...")
    if domain:
        info(f"Domain: {domain}")
    if sni and sni != DEFAULT_SNI:
        info(f"SNI: {sni}")
    if pq:
        info("Post-quantum encryption: enabled (experimental)")
    if warp:
        info("Cloudflare WARP: enabled")
    if not geo_block:
        info("Geo-blocking: disabled (Russian sites accessible)")
    err_console.print()

    # Choose pipeline: full setup (panel + node) or node-only
    if is_panel_host:
        steps = build_setup_steps(ctx)
    else:
        steps = build_node_steps(ctx)

    provisioner = Provisioner(steps)

    conn = resolved.conn
    if not isinstance(conn, ServerConnection):
        fail("No SSH connection available", hint_type="bug")

    results = provisioner.run(conn, ctx)

    # Check for failures
    failed = [r for r in results if r.status == "failed"]
    if failed:
        fail(
            "Setup failed",
            hint=f"Step '{failed[0].name}' failed: {failed[0].detail}\nRun: meridian preflight {ctx.ip}",
            hint_type="system",
        )

    err_console.print()
    ok("All provisioning steps completed")


# ---------------------------------------------------------------------------
# Post-provisioner: Remnawave API configuration
# ---------------------------------------------------------------------------


def _panel_base_url(ip: str, domain: str, secret_path: str) -> str:
    """Build the panel base URL for API calls.

    Panel runs on 127.0.0.1:3000, reverse-proxied by nginx on the secret path.
    For first deploy before nginx is ready, we use SSH tunnel or direct access.
    Once nginx is up, we use https://<host>/<secret_path>.
    """
    host = domain or ip
    return f"https://{host}/{secret_path}"


def _create_api_token(base_url: str, auth_token: str) -> str:
    """Create a long-lived API token using the admin auth token.

    Remnawave's auth tokens (from login/register) are short-lived browser
    session tokens. API endpoints require a separate API token created via
    POST /api/tokens with the 'remnawave-client-type: browser' header.
    The API token is effectively permanent (~274 years).
    """
    import httpx

    resp = httpx.post(
        f"{base_url.rstrip('/')}/api/tokens",
        json={"tokenName": "meridian-provisioner"},
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "X-Remnawave-Client-Type": "browser",
        },
        timeout=30,
        verify=False,
    )
    if resp.status_code not in (200, 201):
        fail(
            f"Could not create API token ({resp.status_code}): {resp.text[:200]}",
            hint="The panel may need a fresh start",
            hint_type="system",
        )
    data = resp.json()
    if isinstance(data, dict) and "response" in data:
        data = data["response"]
    token = data.get("token", "")
    if not token:
        fail("API token creation succeeded but no token returned", hint_type="bug")
    return token


def _generate_reality_keypair(conn: ServerConnection) -> tuple[str, str]:
    """Generate x25519 keypair for Reality using tools available on the server.

    Tries multiple sources: Xray in any running container, xray on host.
    Returns (private_key, public_key) as base64 strings.
    """
    # Try various Xray binaries that might be available
    cmds = [
        "docker exec remnawave-node rw-core x25519 2>/dev/null",
        "docker exec 3x-ui /app/bin/xray-linux-amd64 x25519 2>/dev/null",
        "xray x25519 2>/dev/null",
    ]
    for cmd in cmds:
        result = conn.run(cmd, timeout=15)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        private_key = ""
        public_key = ""
        for raw_line in result.stdout.strip().splitlines():
            ln = raw_line.strip()
            low = ln.lower()
            if "private" in low and ":" in ln:
                private_key = ln.split(":", 1)[1].strip().strip('"')
            elif ("public" in low or "password" in low) and ":" in ln:
                if "hash" not in low:
                    public_key = ln.split(":", 1)[1].strip().strip('"')
        if private_key and public_key:
            return private_key, public_key

    # Last resort: download a temporary Xray binary
    info("Downloading Xray binary for key generation...")
    dl_result = conn.run(
        "curl -sL https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
        " -o /tmp/xray.zip && cd /tmp && unzip -qo xray.zip xray && chmod +x xray"
        " && /tmp/xray x25519 && rm -f /tmp/xray /tmp/xray.zip",
        timeout=60,
    )
    if dl_result.returncode == 0:
        for raw_line in dl_result.stdout.strip().splitlines():
            ln = raw_line.strip()
            low = ln.lower()
            if "private" in low and ":" in ln:
                private_key = ln.split(":", 1)[1].strip().strip('"')
            elif ("public" in low or "password" in low) and ":" in ln:
                if "hash" not in low:
                    public_key = ln.split(":", 1)[1].strip().strip('"')
        if private_key and public_key:
            return private_key, public_key

    fail(
        "Could not generate Reality x25519 keypair",
        hint="Install xray on the server or ensure Docker is running",
        hint_type="system",
    )
    return "", ""  # unreachable


def _get_docker_gateway(conn: ServerConnection) -> str:
    """Get the Docker gateway IP for panel-to-node communication.

    When panel (bridge network) and node (host network) are on the same server,
    the panel cannot reach 127.0.0.1 on the host. It must use the gateway IP
    of its Docker network to reach services on the host network.

    We inspect the panel container's actual network, not the default bridge,
    because the panel runs on a custom 'remnawave-net' network.
    """
    result = conn.run(
        "docker inspect remnawave --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'",
        timeout=15,
    )
    gateway = result.stdout.strip() if result.returncode == 0 else ""
    return gateway or "172.17.0.1"


def _wait_for_panel_api(base_url: str, retries: int = 20, delay: float = 3.0) -> bool:
    """Wait for the panel REST API to become reachable from the deployer."""
    import httpx

    for attempt in range(retries):
        try:
            resp = httpx.get(
                f"{base_url}/api/auth/login",
                timeout=10,
                verify=False,  # Self-signed cert during bootstrap
            )
            # Any response (even 405 Method Not Allowed) means the API is up
            if resp.status_code < 500:
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        if attempt < retries - 1:
            time.sleep(delay)
    return False


def _configure_panel_and_node(
    resolved: ResolvedServer,
    cluster: ClusterConfig,
    domain: str,
    sni: str,
    client_name: str,
    is_first_deploy: bool,
    is_redeploy: bool,
    secret_path: str,
    reality_port: int,
    xhttp_port: int,
    wss_port: int,
    *,
    pq: bool = False,
    geo_block: bool = True,
    xhttp_path: str = "",
    ws_path: str = "",
) -> None:
    """Configure the Remnawave panel via REST API after containers are running.

    For first deploy: register admin, create config profile, register node,
    create hosts, create first client.

    For redeploy: verify panel access, update node if needed.

    For new node: register node with existing panel, create hosts.
    """
    from meridian import __version__

    err_console.print()
    info("Configuring panel via API...")

    if is_first_deploy:
        _setup_first_deploy(
            resolved=resolved,
            cluster=cluster,
            domain=domain,
            sni=sni,
            client_name=client_name,
            secret_path=secret_path,
            reality_port=reality_port,
            xhttp_port=xhttp_port,
            wss_port=wss_port,
            pq=pq,
            geo_block=geo_block,
            version=__version__,
            xhttp_path=xhttp_path,
            ws_path=ws_path,
        )
    elif is_redeploy:
        _setup_redeploy(
            resolved=resolved,
            cluster=cluster,
            domain=domain,
            sni=sni,
            version=__version__,
        )
    else:
        _setup_new_node(
            resolved=resolved,
            cluster=cluster,
            domain=domain,
            sni=sni,
            reality_port=reality_port,
            xhttp_port=xhttp_port,
            wss_port=wss_port,
            version=__version__,
            xhttp_path=xhttp_path,
            ws_path=ws_path,
        )


def _setup_first_deploy(
    resolved: ResolvedServer,
    cluster: ClusterConfig,
    domain: str,
    sni: str,
    client_name: str,
    secret_path: str,
    reality_port: int,
    xhttp_port: int,
    wss_port: int,
    *,
    pq: bool,
    geo_block: bool,
    version: str,
    xhttp_path: str = "",
    ws_path: str = "",
) -> None:
    """First deploy: full panel bootstrap from scratch."""
    base_url = _panel_base_url(resolved.ip, domain, secret_path)

    # Wait for panel API to become accessible
    info("Waiting for panel API...")
    if not _wait_for_panel_api(base_url):
        fail(
            "Panel API is not reachable",
            hint=(
                f"Panel should be at {base_url}\n"
                f"Check: ssh {resolved.user}@{resolved.ip} docker logs remnawave --tail 30"
            ),
            hint_type="system",
        )

    # Register admin user
    admin_user = f"meridian-{secrets.token_hex(4)}"
    # Remnawave requires: ≥24 chars, uppercase + lowercase + numbers
    admin_pass = f"Mx{secrets.token_hex(16)}9A"

    try:
        auth_token = MeridianPanel.register_admin(base_url, admin_user, admin_pass)
    except RemnawaveError as e:
        # Admin may already exist on re-run after partial failure
        try:
            auth_token = MeridianPanel.login(base_url, admin_user, admin_pass)
        except RemnawaveError:
            fail(
                f"Could not register or login to panel: {e}",
                hint="Panel may need a fresh start: meridian teardown, then redeploy",
                hint_type="system",
            )
    ok("Panel admin registered")

    # Save admin credentials BEFORE API token step (lockout prevention:
    # if API token creation fails, we can still login with these creds)
    sub_path = secrets.token_hex(8)
    cluster.panel = PanelConfig(
        url=base_url,
        api_token="",  # filled after API token creation
        admin_user=admin_user,
        admin_pass=admin_pass,
        server_ip=resolved.ip,
        ssh_user=resolved.user,
        ssh_port=getattr(resolved.conn, "port", 22),
        secret_path=secret_path,
        sub_path=sub_path,
        deployed_with=version,
    )
    cluster.save()

    # Create a long-lived API token (auth token is browser-session only)
    api_token = _create_api_token(base_url, auth_token)
    ok("API token created")

    # Update cluster with the API token
    cluster.panel.api_token = api_token
    cluster.save()

    with MeridianPanel(base_url, api_token) as panel:
        # Create config profile (Xray inbound definitions)
        profile_name = "meridian-default"
        xray_result = _build_xray_config(
            resolved.conn,
            sni=sni,
            reality_port=reality_port,
            xhttp_port=xhttp_port,
            wss_port=wss_port,
            domain=domain,
            pq=pq,
            geo_block=geo_block,
            xhttp_path=xhttp_path,
            ws_path=ws_path,
        )
        xray_config = xray_result["config"]
        reality_public_key = xray_result["reality_public_key"]
        reality_short_id = xray_result["reality_short_id"]

        try:
            profile = panel.create_config_profile(profile_name, xray_config)
            cluster.config_profile_uuid = profile.uuid
            cluster.config_profile_name = profile.name
            ok("Config profile created")
        except RemnawaveError as e:
            fail(f"Failed to create config profile: {e}", hint_type="system")

        # Cache inbound references from the profile
        _cache_inbounds(panel, cluster)

        # Register this server as a node
        # For same-server deployments (panel + node co-located), the panel runs
        # in a Docker bridge network and cannot reach the node on 127.0.0.1.
        # Use the Docker bridge gateway IP so the panel can reach the node.
        node_address = _get_docker_gateway(resolved.conn)
        node_name = domain or resolved.ip
        try:
            inbound_uuids = [ref.uuid for ref in cluster.inbounds.values() if isinstance(ref, InboundRef) and ref.uuid]
            node_creds = panel.create_node(
                name=node_name,
                address=node_address,
                port=REMNAWAVE_NODE_API_PORT,
                config_profile_uuid=cluster.config_profile_uuid,
                inbound_uuids=inbound_uuids,
            )
            ok(f"Node registered: {node_name}")
        except RemnawaveError as e:
            fail(f"Failed to register node: {e}", hint_type="system")

        # Store node_secret_key so the DeployRemnawaveNode step can use it
        # (in the current flow, the node container is already started by the
        # provisioner -- this writes the secret to the node's .env and restarts)
        _deploy_node_container(resolved.conn, node_creds.secret_key)

        # Save node entry to cluster
        node_entry = NodeEntry(
            ip=resolved.ip,
            uuid=node_creds.uuid,
            name=node_name,
            ssh_user=resolved.user,
            ssh_port=getattr(resolved.conn, "port", 22),
            sni=sni,
            domain=domain,
            is_panel_host=True,
            deployed_with=version,
            xhttp_path=xhttp_path,
            ws_path=ws_path,
            reality_public_key=reality_public_key,
            reality_short_id=reality_short_id,
        )
        cluster.nodes.append(node_entry)
        cluster.save()

        # Create direct hosts for this node's protocols
        _create_hosts_for_node(panel, cluster, resolved.ip, domain, sni, reality_port)

        # Create first client
        try:
            existing_user = panel.get_user(client_name)
            if existing_user:
                info(f"Client '{client_name}' already exists")
            else:
                panel.create_user(client_name)
                ok(f"Client '{client_name}' created")
        except RemnawaveError as e:
            warn(f"Could not create client '{client_name}': {e}")

    ok("Panel configuration complete")


def _setup_redeploy(
    resolved: ResolvedServer,
    cluster: ClusterConfig,
    domain: str,
    sni: str,
    version: str,
) -> None:
    """Redeploy: verify panel access, update node metadata."""
    if not cluster.panel.api_token:
        fail(
            "Cluster config exists but has no API token",
            hint="Run: meridian teardown, then redeploy from scratch",
            hint_type="system",
        )

    try:
        with MeridianPanel(cluster.panel.url, cluster.panel.api_token) as panel:
            if not panel.ping():
                fail(
                    "Cannot reach panel API",
                    hint=f"Panel URL: {cluster.panel.url}\nCheck panel logs on {cluster.panel.server_ip}",
                    hint_type="system",
                )
            ok("Panel API accessible")

            # Update node entry metadata
            node = cluster.find_node(resolved.ip)
            if node:
                node.sni = sni or node.sni
                node.domain = domain or node.domain
                node.deployed_with = version
                cluster.save()
                ok("Node metadata updated")

    except RemnawaveError as e:
        fail(f"Panel API error: {e}", hint_type="system")


def _setup_new_node(
    resolved: ResolvedServer,
    cluster: ClusterConfig,
    domain: str,
    sni: str,
    reality_port: int,
    xhttp_port: int,
    wss_port: int,
    version: str,
    *,
    xhttp_path: str = "",
    ws_path: str = "",
) -> None:
    """Add a new node to an existing cluster."""
    if not cluster.panel.api_token:
        fail(
            "No panel configured -- deploy a panel first with: meridian deploy <IP>",
            hint_type="user",
        )

    try:
        with MeridianPanel(cluster.panel.url, cluster.panel.api_token) as panel:
            if not panel.ping():
                fail(
                    "Cannot reach panel API",
                    hint=f"Panel URL: {cluster.panel.url}\nCheck panel logs on {cluster.panel.server_ip}",
                    hint_type="system",
                )

            node_name = domain or resolved.ip
            inbound_uuids = [ref.uuid for ref in cluster.inbounds.values() if isinstance(ref, InboundRef) and ref.uuid]
            node_creds = panel.create_node(
                name=node_name,
                address=resolved.ip,
                port=REMNAWAVE_NODE_API_PORT,
                config_profile_uuid=cluster.config_profile_uuid,
                inbound_uuids=inbound_uuids,
            )
            ok(f"Node registered: {node_name}")

            # Deploy the node container with the secret key
            _deploy_node_container(resolved.conn, node_creds.secret_key)

            # Save node entry
            # Reuse Reality keys from existing node (shared config profile)
            existing_node = cluster.panel_node
            node_entry = NodeEntry(
                ip=resolved.ip,
                uuid=node_creds.uuid,
                name=node_name,
                ssh_user=resolved.user,
                ssh_port=getattr(resolved.conn, "port", 22),
                sni=sni,
                domain=domain,
                is_panel_host=False,
                deployed_with=version,
                xhttp_path=xhttp_path,
                ws_path=ws_path,
                reality_public_key=existing_node.reality_public_key if existing_node else "",
                reality_short_id=existing_node.reality_short_id if existing_node else "",
            )
            cluster.nodes.append(node_entry)
            cluster.save()

            # Create hosts for the new node
            _create_hosts_for_node(panel, cluster, resolved.ip, domain, sni, reality_port)

    except RemnawaveError as e:
        fail(f"Panel API error: {e}", hint_type="system")

    ok("New node configured")


# ---------------------------------------------------------------------------
# Panel API helpers
# ---------------------------------------------------------------------------


def _build_xray_config(
    conn: ServerConnection,
    sni: str,
    reality_port: int,
    xhttp_port: int,
    wss_port: int,
    domain: str,
    *,
    pq: bool,
    geo_block: bool,
    xhttp_path: str = "",
    ws_path: str = "",
) -> dict:
    """Build the Xray configuration for a Remnawave config profile.

    This defines the inbounds that the node will run. The actual Xray
    config is managed by Remnawave, but we provide the template.

    Returns a dict with keys:
      - "config": the Xray config dict
      - "reality_public_key": the Reality public key
      - "reality_short_id": the Reality short ID
    """
    # Base config with DNS and routing
    config: dict = {
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": [
                {"address": "https://dns.google/dns-query", "domains": ["geosite:geolocation-!cn"]},
                "8.8.8.8",
            ],
        },
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [],
        },
        "inbounds": [],
    }

    # Geo-blocking rules
    if geo_block:
        config["routing"]["rules"].extend(
            [
                {"type": "field", "domain": ["geosite:category-ru"], "outboundTag": "block"},
                {"type": "field", "ip": ["geoip:ru"], "outboundTag": "block"},
            ]
        )

    # Block private IPs (prevent probing internal network)
    config["routing"]["rules"].append({"type": "field", "ip": ["geoip:private"], "outboundTag": "block"})

    # Outbounds
    config["outbounds"] = [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ]

    # Reality inbound (primary -- always present)
    # Generate x25519 keypair and short ID for Reality camouflage
    private_key, public_key = _generate_reality_keypair(conn)
    short_id = secrets.token_hex(4)  # 8-char hex

    reality_inbound = {
        "tag": "vless-reality",
        "protocol": "vless",
        "listen": "127.0.0.1",
        "port": reality_port,
        "settings": {
            "clients": [],
            "decryption": "none",
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "dest": f"{sni}:443",
                "serverNames": [sni],
                "privateKey": private_key,
                "shortIds": [short_id],
                "fingerprint": "chrome",
            },
        },
    }
    if pq:
        reality_inbound["streamSettings"]["realitySettings"]["fingerprint"] = "chrome"
    config["inbounds"].append(reality_inbound)

    # XHTTP inbound (enhanced stealth -- behind nginx reverse proxy)
    xhttp_stream = {
        "network": "xhttp",
        "security": "none",
    }
    if xhttp_path:
        xhttp_stream["xhttpSettings"] = {"path": f"/{xhttp_path}"}
    xhttp_inbound = {
        "tag": "vless-xhttp",
        "protocol": "vless",
        "listen": "127.0.0.1",
        "port": xhttp_port,
        "settings": {
            "clients": [],
            "decryption": "none",
        },
        "streamSettings": xhttp_stream,
    }
    config["inbounds"].append(xhttp_inbound)

    # WSS inbound (CDN fallback -- domain mode only)
    if domain:
        ws_stream = {
            "network": "ws",
            "security": "none",
        }
        if ws_path:
            ws_stream["wsSettings"] = {"path": f"/{ws_path}"}
        wss_inbound = {
            "tag": "vless-wss",
            "protocol": "vless",
            "listen": "127.0.0.1",
            "port": wss_port,
            "settings": {
                "clients": [],
                "decryption": "none",
            },
            "streamSettings": ws_stream,
        }
        config["inbounds"].append(wss_inbound)

    return {
        "config": config,
        "reality_public_key": public_key,
        "reality_short_id": short_id,
    }


def _cache_inbounds(panel: MeridianPanel, cluster: ClusterConfig) -> None:
    """Fetch inbound definitions from the panel and cache their UUIDs."""
    try:
        inbounds = panel.list_inbounds()
        tag_map = {
            "vless-reality": ProtocolKey.REALITY,
            "vless-xhttp": ProtocolKey.XHTTP,
            "vless-wss": ProtocolKey.WSS,
        }
        for ib in inbounds:
            key = tag_map.get(ib.tag)
            if key:
                cluster.inbounds[str(key)] = InboundRef(uuid=ib.uuid, tag=ib.tag)
        ok(f"Cached {len(cluster.inbounds)} inbound references")
    except RemnawaveError as e:
        warn(f"Could not cache inbound references: {e}")


def _create_hosts_for_node(
    panel: MeridianPanel,
    cluster: ClusterConfig,
    node_ip: str,
    domain: str,
    sni: str,
    reality_port: int,
) -> None:
    """Create direct host entries for a node's protocols."""
    host_address = domain or node_ip

    # Reality host (direct IP, port 443 or computed)
    reality_ref = cluster.get_inbound(ProtocolKey.REALITY)
    if reality_ref and reality_ref.uuid:
        try:
            panel.create_host(
                remark=f"reality-{node_ip}",
                address=node_ip,
                port=reality_port,
                config_profile_uuid=cluster.config_profile_uuid,
                inbound_uuid=reality_ref.uuid,
                sni=sni,
                fingerprint="chrome",
                security_layer="DEFAULT",
            )
            ok(f"Host created: Reality via {node_ip}:{reality_port}")
        except RemnawaveError as e:
            warn(f"Could not create Reality host: {e}")

    # XHTTP host (via domain or IP, port 443 through nginx)
    xhttp_ref = cluster.get_inbound(ProtocolKey.XHTTP)
    if xhttp_ref and xhttp_ref.uuid:
        try:
            panel.create_host(
                remark=f"xhttp-{host_address}",
                address=host_address,
                port=443,
                config_profile_uuid=cluster.config_profile_uuid,
                inbound_uuid=xhttp_ref.uuid,
                security_layer="TLS",
            )
            ok(f"Host created: XHTTP via {host_address}:443")
        except RemnawaveError as e:
            warn(f"Could not create XHTTP host: {e}")

    # WSS host (domain mode only, port 443 through CDN)
    if domain:
        wss_ref = cluster.get_inbound(ProtocolKey.WSS)
        if wss_ref and wss_ref.uuid:
            try:
                panel.create_host(
                    remark=f"wss-{domain}",
                    address=domain,
                    port=443,
                    config_profile_uuid=cluster.config_profile_uuid,
                    inbound_uuid=wss_ref.uuid,
                    security_layer="TLS",
                )
                ok(f"Host created: WSS via {domain}:443")
            except RemnawaveError as e:
                warn(f"Could not create WSS host: {e}")


def _deploy_node_container(conn: ServerConnection, secret_key: str) -> None:
    """Deploy the Remnawave node container with the given secret key.

    Creates /opt/remnanode, writes docker-compose.yml and .env, pulls the
    image, and starts the container. Called from the post-provisioner phase
    after the panel API has registered the node and returned the mTLS secret.
    """
    from meridian.config import REMNAWAVE_NODE_API_PORT, REMNAWAVE_NODE_DIR, REMNAWAVE_NODE_IMAGE
    from meridian.provision.remnawave_node import _render_node_compose, _render_node_env

    node_dir = REMNAWAVE_NODE_DIR
    q_dir = shlex.quote(node_dir)

    # Create directory
    result = conn.run(f"mkdir -p {node_dir} && chmod 700 {node_dir}", timeout=15)
    if result.returncode != 0:
        warn(f"Could not create {node_dir}: {result.stderr.strip()[:200]}")
        return

    # Write .env
    env_content = _render_node_env(REMNAWAVE_NODE_API_PORT, secret_key)
    env_path = f"{node_dir}/.env"
    write_env = f"cat > {shlex.quote(env_path)} << 'MERIDIAN_EOF'\n{env_content}MERIDIAN_EOF"
    conn.run(write_env, timeout=15)
    conn.run(f"chmod 600 {shlex.quote(env_path)}", timeout=15)

    # Write docker-compose.yml
    compose_content = _render_node_compose(REMNAWAVE_NODE_IMAGE, REMNAWAVE_NODE_API_PORT)
    compose_path = f"{node_dir}/docker-compose.yml"
    write_compose = f"cat > {shlex.quote(compose_path)} << 'MERIDIAN_EOF'\n{compose_content}MERIDIAN_EOF"
    conn.run(write_compose, timeout=15)

    # Pull image
    info("Pulling Remnawave node image...")
    pull_ok = False
    for attempt in range(3):
        result = conn.run(f"cd {q_dir} && docker compose pull", timeout=300)
        if result.returncode == 0:
            pull_ok = True
            break
        if attempt < 2:
            time.sleep(10)

    if not pull_ok:
        warn("Could not pull node image — node may not start")
        return

    # Start container
    result = conn.run(f"cd {q_dir} && docker compose up -d", timeout=120)
    if result.returncode != 0:
        warn(f"Node container failed to start: {result.stderr.strip()[:200]}")
        return

    ok("Remnawave node deployed")

    # Allow Docker internal traffic to reach the node API port
    # (panel in bridge network → node on host via gateway IP)
    from meridian.config import REMNAWAVE_NODE_API_PORT

    conn.run(
        f"ufw allow from 172.16.0.0/12 to any port {REMNAWAVE_NODE_API_PORT} proto tcp"
        f" comment 'Meridian node API (Docker internal)' 2>/dev/null; true",
        timeout=15,
    )


# ---------------------------------------------------------------------------
# Port check
# ---------------------------------------------------------------------------


def _check_ports(conn: ServerConnection, ip: str, yes: bool) -> None:
    """Check that ports 443 and 80 are available before deploying.

    Allows re-deploy over existing Meridian processes.
    Loops with retry prompt if a non-Meridian process holds a port.
    """
    allowed = {"nginx", "xray", "haproxy", "caddy", "remnawave", "remnawave-node", "docker-proxy"}

    for port in (443, 80):
        while True:
            result = conn.run(f"ss -tlnp sport = :{port} 2>/dev/null | grep LISTEN", timeout=10)
            if not result.stdout.strip():
                break  # port free

            match = re.search(r'users:\(\("([^"]*)"', result.stdout)
            proc = match.group(1) if match else "unknown"
            if proc in allowed:
                break  # Meridian's own process -- OK for re-deploy

            warn(f"Port {port} is in use by {proc}")
            err_console.print(f"  [dim]Port {port} must be free for Meridian.[/dim]")
            err_console.print(f"  [dim]Stop {proc} and retry, or press Ctrl+C to abort.[/dim]")
            err_console.print()

            if yes:
                fail(
                    f"Port {port} is occupied by {proc}",
                    hint=f"Stop {proc} first: sudo systemctl stop {proc}",
                    hint_type="user",
                )

            choice = choose("Retry?", ["Yes", "No"])
            if choice == 2:
                fail("Aborted -- port conflict", hint_type="user")


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------


def _interactive_wizard(
    sni: str,
    domain: str,
    harden: bool,
    yes: bool,
    client_name: str = "",
    server_name: str = "",
    icon: str = "",
    color: str = "",
    pq: bool = False,
    warp: bool = False,
    geo_block: bool = True,
) -> tuple[str, str, str, str, bool, str, str, str, str, bool, bool, bool]:
    """Interactive deployment wizard.

    Returns (ip, user, sni, domain, harden,
             client_name, server_name, icon, color, pq, warp, geo_block).
    """
    import os

    # --- Protocol explanation ---
    err_console.print()
    info("Protocol: VLESS + Reality")
    err_console.print("  [dim]Your server impersonates a real website -- censors see[/dim]")
    err_console.print("  [dim]normal HTTPS traffic, not a VPN connection.[/dim]")
    err_console.print()

    # --- Server IP ---
    detected_ip = detect_public_ip()
    is_local = False

    # Offer local deployment if running as root with a public IP
    if detected_ip and os.getuid() == 0:
        info(f"Detected: running as root on this server ({detected_ip})")
        err_console.print()
        choice = choose(
            "Deploy target",
            [
                f"This server ({detected_ip}) -- local mode",
                "Another server -- enter IP",
            ],
        )
        if choice == 1:
            server_ip = "local"
            ssh_user = "root"
            is_local = True
        else:
            is_local = False

    if not is_local:
        while True:
            server_ip = prompt("Server IP address", default=detected_ip)
            if is_ip(server_ip) or is_local_keyword(server_ip):
                break
            err_console.print("  [error]Enter a valid IP address (e.g. 123.45.67.89)[/error]")

        if is_local_keyword(server_ip):
            is_local = True
            ssh_user = "root"
        else:
            # --- SSH user ---
            while True:
                ssh_user = prompt("SSH user", default="root")
                if re.match(r"^[a-zA-Z0-9._-]+$", ssh_user):
                    break
                err_console.print("  [error]Use letters, numbers, dots, hyphens, and underscores only[/error]")
            if ssh_user != "root":
                err_console.print("  [dim](sudo will be used for privileged operations)[/dim]")

    # --- Server hardening ---
    if not yes:
        err_console.print()
        err_console.print("  [bold]Server hardening[/bold]")
        err_console.print("  [dim]Disables password SSH login and enables firewall[/dim]")
        err_console.print("  [dim](allows ports 22, 80, 443 only). Skip if you have[/dim]")
        err_console.print("  [dim]other services running on this server.[/dim]")
        err_console.print()
        choice = choose(
            "Choose",
            [
                "Yes -- harden SSH and firewall [dim](recommended)[/dim]",
                "No -- keep current settings",
            ],
        )
        if choice == 2:
            harden = False
            warn("Skipping SSH hardening and firewall")
        else:
            harden = True

    # --- Camouflage target (SNI) ---
    if not sni:
        err_console.print()
        err_console.print("  [bold]Camouflage target[/bold]")
        err_console.print("  [dim]Pick any popular website (you don't need to own it).[/dim]")
        err_console.print("  [dim]Your server will impersonate it -- censors probing see[/dim]")
        err_console.print("  [dim]that real site's certificate. Scanning finds targets on[/dim]")
        err_console.print("  [dim]the same network, which are hardest to distinguish.[/dim]")
        err_console.print()

        if not yes:
            choice = choose(
                "Camouflage",
                [
                    "Scan for optimal target (~1 minute)",
                    "Enter manually",
                    f"Skip -- use default ({DEFAULT_SNI})",
                ],
            )
            if choice == 2:
                sni = prompt("SNI domain (e.g. example.com)")
            elif choice == 1:
                # Establish connection for scan
                try:
                    scan_ip = detected_ip if is_local else server_ip
                    conn = ServerConnection(ip=scan_ip, user=ssh_user, local_mode=is_local)
                    if not is_local:
                        conn.detect_local_mode()
                        if not conn.local_mode:
                            conn.check_ssh()

                    from meridian.commands.scan import scan_for_sni

                    candidates = scan_for_sni(conn, scan_ip)

                    if candidates:
                        top = candidates[:5]
                        options = list(top) + [f"[dim]Skip -- use default ({DEFAULT_SNI})[/dim]"]
                        err_console.print()
                        pick = choose("Choose", options)
                        if pick <= len(top):
                            sni = top[pick - 1]
                    else:
                        warn("No targets found on the same network")
                except Exception:
                    warn("Could not connect to scan. You can run 'meridian scan' later.")

        if not sni:
            sni = DEFAULT_SNI

    # --- Domain (optional but strongly recommended) ---
    err_console.print()
    err_console.print("  [bold]Domain[/bold] [dim](strongly recommended)[/dim]")
    err_console.print("  [dim]Makes your server indistinguishable from a normal website.[/dim]")
    err_console.print("  [dim]Without a domain, probers see an IP-only certificate --[/dim]")
    err_console.print("  [dim]a valid but less common profile. Also enables CDN fallback.[/dim]")
    err_console.print("  [dim]Guide: getmeridian.org/docs/en/domain-mode/[/dim]")

    if not yes:
        domain_input = prompt("Domain (leave blank to skip)", default=domain or "")
        if domain_input and domain_input != "skip":
            domain = domain_input
        elif not domain_input or domain_input == "skip":
            domain = ""
    elif not domain:
        domain = ""

    # --- Branding: server name ---
    if not yes and not server_name:
        err_console.print()
        err_console.print("  [bold]Personalize[/bold]")
        err_console.print("  [dim]Make the connection page yours. Your friends see this.[/dim]")
        err_console.print()
        server_name = prompt("Server name", default="My VPN")

    # --- Branding: icon ---
    if not yes and not icon:
        from meridian.branding import ICON_SUGGESTIONS

        err_console.print()
        err_console.print("  [bold]Server icon[/bold]")
        grid = "    "
        for i, emoji in enumerate(ICON_SUGGESTIONS, 1):
            grid += f"{i}. {emoji}  "
        err_console.print(grid)
        err_console.print()
        icon_input = prompt("Pick a number, paste an emoji, or an image URL", default="1")
        if icon_input.isdigit():
            idx = int(icon_input) - 1
            if 0 <= idx < len(ICON_SUGGESTIONS):
                icon = ICON_SUGGESTIONS[idx]
        if not icon:
            from meridian.branding import process_icon

            icon = process_icon(icon_input)
    elif icon:
        # CLI flag provided -- process it
        from meridian.branding import process_icon

        processed = process_icon(icon)
        if processed:
            icon = processed

    # --- Branding: color palette ---
    if not yes and not color:
        from meridian.branding import PALETTE_LABELS, PALETTES

        err_console.print()
        err_console.print("  [bold]Color palette[/bold]")
        palette_names = list(PALETTES.keys())
        options = []
        for pname in palette_names:
            marker = " [dim](default)[/dim]" if pname == "ocean" else ""
            options.append(f"{PALETTE_LABELS[pname]}{marker}")
        err_console.print()
        color_pick = choose("Choose", options)
        idx = color_pick - 1
        if 0 <= idx < len(palette_names):
            color = palette_names[idx]
    elif color:
        from meridian.branding import validate_color

        color = validate_color(color) or "ocean"

    if not color:
        color = "ocean"

    # --- Client name ---
    if not yes and not client_name:
        err_console.print()
        err_console.print("  [bold]First client[/bold]")
        err_console.print("  [dim]Name for the first connection profile (you can add more later).[/dim]")
        err_console.print()
        client_name = prompt("Client name", default="default")

    if not client_name:
        client_name = "default"

    # --- Post-quantum encryption ---
    if not yes and not pq:
        err_console.print()
        err_console.print("  [bold]Post-quantum encryption[/bold] [dim](experimental)[/dim]")
        err_console.print("  [dim]Adds ML-KEM-768 hybrid encryption on top of Reality.[/dim]")
        err_console.print("  [dim]Only tested with Happ and v2RayTun. Some apps may not connect.[/dim]")
        err_console.print()
        choice = choose(
            "Choose",
            [
                "No -- standard encryption [dim](all apps)[/dim]",
                "Yes -- post-quantum [dim](tested: Happ, v2RayTun)[/dim]",
            ],
        )
        if choice == 2:
            pq = True

    # --- Cloudflare WARP ---
    if not yes and not warp:
        err_console.print()
        err_console.print("  [bold]Cloudflare WARP[/bold] [dim](optional)[/dim]")
        err_console.print("  [dim]Routes outgoing traffic through Cloudflare so websites[/dim]")
        err_console.print("  [dim]see a Cloudflare IP, not your server's real IP.[/dim]")
        err_console.print()
        err_console.print("  [dim]Useful when:[/dim]")
        err_console.print("  [dim]  * Websites block datacenter/VPS IP ranges[/dim]")
        err_console.print("  [dim]  * You want to hide the VPS IP from destination sites[/dim]")
        err_console.print()
        err_console.print("  [dim]Not needed when:[/dim]")
        err_console.print("  [dim]  * Normal browsing already works fine through the proxy[/dim]")
        err_console.print("  [dim]  * You want maximum speed (WARP adds an extra hop)[/dim]")
        err_console.print()
        choice = choose(
            "Choose",
            [
                "No -- direct connection [dim](default, fastest)[/dim]",
                "Yes -- route through Cloudflare WARP",
            ],
        )
        if choice == 2:
            warp = True

    # --- Geo-blocking ---
    if not yes and geo_block:
        err_console.print()
        err_console.print("  [bold]Geo-blocking[/bold]")
        err_console.print("  [dim]Blocks access to Russian websites and IPs through[/dim]")
        err_console.print("  [dim]the proxy (geosite:category-ru + geoip:ru).[/dim]")
        err_console.print()
        err_console.print("  [dim]Why enable:[/dim]")
        err_console.print("  [dim]  * Prevents your VPN server IP from appearing in logs[/dim]")
        err_console.print("  [dim]    of Russian services -- reduces risk of it being blocked[/dim]")
        err_console.print("  [dim]  * Russian sites work fine without a VPN anyway[/dim]")
        err_console.print()
        err_console.print("  [dim]Why disable:[/dim]")
        err_console.print("  [dim]  * You need to access .ru sites through the proxy[/dim]")
        err_console.print("  [dim]  * You want all traffic to go through the VPN with no[/dim]")
        err_console.print("  [dim]    exceptions[/dim]")
        err_console.print()
        choice = choose(
            "Choose",
            [
                "Yes -- block Russian traffic [dim](recommended, protects server IP)[/dim]",
                "No -- allow all traffic [dim](Russian sites accessible through proxy)[/dim]",
            ],
        )
        if choice == 2:
            geo_block = False

    # --- Summary panel ---
    from rich.panel import Panel

    protocol_line = "VLESS + Reality (TCP)\n           + XHTTP fallback (same port)"
    if domain:
        protocol_line += f"\n           + CDN fallback ({domain})"

    encryption_line = ""
    if pq:
        encryption_line = "\nEncryption: Post-quantum (ML-KEM-768 hybrid) [dim]experimental[/dim]"

    warp_line = ""
    if warp:
        warp_line = "\nWARP:       Outgoing traffic via Cloudflare"

    geo_block_line = (
        "\nGeo-block:  Enabled (.ru / Russian IP traffic blocked)"
        if geo_block
        else "\nGeo-block:  Disabled (Russian sites accessible)"
    )

    icon_display = icon if icon and not icon.startswith("data:") else ""
    branding_line = ""
    if server_name or icon_display or color:
        parts = []
        if icon_display:
            parts.append(icon_display)
        if server_name:
            parts.append(server_name)
        if color:
            parts.append(f"[dim]{color} palette[/dim]")
        branding_line = f"\nBranding:   {' '.join(parts)}"

    server_label = f"this server ({detected_ip}) -- local mode" if is_local else f"{ssh_user}@{server_ip}"
    harden_label = "SSH hardened + firewall" if harden else "skipped"
    summary = (
        f"Server:     {server_label}\n"
        f"Protocol:   {protocol_line}\n"
        f"Camouflage: {sni}\n"
        f"Hardening:  {harden_label}\n"
        f"Client:     {client_name}\n"
        f"Mode:       {'Domain mode (best stealth + CDN fallback)' if domain else 'IP-only (works without a domain)'}"
        f"{encryption_line}"
        f"{warp_line}"
        f"{geo_block_line}"
        f"{branding_line}"
    )

    err_console.print()
    err_console.print(Panel(summary, title="[bold]Deployment plan[/bold]", border_style="cyan", padding=(0, 2)))
    err_console.print()

    # --- Confirm ---
    if not yes:
        if is_local:
            confirm(f"Deploy locally on this server ({detected_ip})?")
        else:
            confirm(f"Deploy to {ssh_user}@{server_ip}?")
    err_console.print()

    return server_ip, ssh_user, sni, domain, harden, client_name, server_name, icon, color, pq, warp, geo_block


# ---------------------------------------------------------------------------
# Success output
# ---------------------------------------------------------------------------


def _build_redeploy_command(
    resolved: ResolvedServer,
    *,
    sni: str,
    domain: str,
    client_name: str,
    harden: bool,
    server_name: str,
    icon: str,
    color: str,
    pq: bool,
    warp: bool,
    geo_block: bool,
) -> str:
    """Build a non-interactive meridian deploy command that reproduces the current config."""
    parts = ["meridian deploy", shlex.quote(resolved.ip)]

    if resolved.user != "root":
        parts.append(f"--user {shlex.quote(resolved.user)}")
    if sni and sni != DEFAULT_SNI:
        parts.append(f"--sni {shlex.quote(sni)}")
    if domain:
        parts.append(f"--domain {shlex.quote(domain)}")
    if client_name and client_name != "default":
        parts.append(f"--client-name {shlex.quote(client_name)}")
    if not harden:
        parts.append("--no-harden")
    if pq:
        parts.append("--pq")
    if warp:
        parts.append("--warp")
    if not geo_block:
        parts.append("--no-geo-block")
    if server_name:
        parts.append(f"--display-name {shlex.quote(server_name)}")
    if icon:
        parts.append(f"--icon {shlex.quote(icon)}")
    if color and color != "ocean":
        parts.append(f"--color {shlex.quote(color)}")
    parts.append("--yes")

    return " ".join(parts)


def _print_success(
    resolved: ResolvedServer,
    cluster: ClusterConfig,
    client_name: str,
    domain: str,
    *,
    redeploy_cmd: str,
) -> None:
    """Print success output after deployment."""
    client_label = client_name or "default"
    server_ip = resolved.ip

    # Build subscription URL if panel is configured
    sub_url = ""
    if cluster.panel.url and cluster.panel.api_token:
        try:
            with MeridianPanel(cluster.panel.url, cluster.panel.api_token) as panel:
                user = panel.get_user(client_label)
                if user and user.short_uuid:
                    sub_url = panel.get_subscription_url(user.short_uuid)
        except RemnawaveError:
            pass

    err_console.print("\n  [ok][bold]Done![/bold][/ok]\n")
    ok("Your proxy server is live and ready to use.")
    err_console.print()
    err_console.print("  [bold]Next steps:[/bold]\n")

    if sub_url:
        err_console.print("  [ok]1.[/ok] Share this subscription link with whoever needs access:")
        err_console.print(f"     [bold]{sub_url}[/bold]")
        err_console.print("     [dim](Add to any Xray/V2Ray client as a subscription URL)[/dim]\n")
    else:
        err_console.print("  [ok]1.[/ok] View connection details:")
        err_console.print(f"     [info]meridian client show {client_label}[/info]\n")

    err_console.print("  [ok]2.[/ok] Test that the proxy works:")
    err_console.print(f"     [info]meridian test {server_ip}[/info]")
    err_console.print("     [dim]Run it after deploy/redeploy to verify the live server state.[/dim]\n")

    if cluster.panel.url:
        err_console.print("  [ok]3.[/ok] Manage clients:")
        err_console.print("     [info]meridian client add alice[/info]")
        err_console.print("     [info]meridian client list[/info]\n")

    next_step = 4
    if domain:
        err_console.print(f"  [ok]{next_step}.[/ok] Cloudflare setup:")
        err_console.print(f"     [dim]A record {domain} -> {server_ip}[/dim]")
        err_console.print("     [dim]Keep it DNS only (grey cloud) during deploy/redeploy[/dim]")
        err_console.print("     [dim]After deploy succeeds: switch to Proxied (orange cloud)[/dim]")
        err_console.print("     [dim]Set SSL/TLS to Full (Strict) and enable WebSockets[/dim]\n")
        err_console.print("     [dim]Disable features that inject scripts or rewrite HTML on this hostname[/dim]")
        err_console.print("     [dim](for example Website Analytics / RUM), or the connection page can break[/dim]\n")
        next_step = 5

    err_console.print(f"  [ok]{next_step}.[/ok] Add a relay for resilience (optional):")
    err_console.print(f"     [info]meridian relay deploy RELAY_IP --exit {server_ip}[/info]")
    err_console.print("     [dim]Routes through a domestic IP when the exit gets blocked[/dim]\n")

    err_console.print()
    line()

    # Redeploy command
    err_console.print("\n  [dim]Re-deploy with the same settings:[/dim]")
    err_console.print(f"  [dim]  {redeploy_cmd}[/dim]")

    # Panel access for advanced users
    if cluster.panel.url:
        err_console.print("\n  [dim]Remnawave panel (advanced -- manage nodes, monitor traffic):[/dim]")
        err_console.print(f"  [dim]  {cluster.panel.url}[/dim]")

    err_console.print("\n  [dim]Feedback & issues: https://github.com/uburuntu/meridian/issues[/dim]\n")


def _offer_relay(resolved: ResolvedServer, yes: bool) -> None:
    """Offer to deploy a relay node after successful exit server deploy."""
    if yes:
        return  # Don't prompt in non-interactive mode

    err_console.print()
    err_console.print("  [bold]Add a relay node?[/bold] [dim](optional)[/dim]")
    err_console.print("  [dim]A relay is a domestic server that forwards traffic to[/dim]")
    err_console.print("  [dim]this exit server. Useful when the IP gets blocked.[/dim]")
    err_console.print()

    choice = choose(
        "Set up a relay?",
        [
            "No -- skip for now",
            "Yes -- add a relay node",
        ],
    )
    if choice == 1:
        err_console.print(f"  [dim]You can add one later: meridian relay deploy RELAY_IP --exit {resolved.ip}[/dim]")
        return

    relay_ip = prompt("Relay server IP")
    if not is_ip(relay_ip):
        warn(f"Invalid IP. Set up later: meridian relay deploy RELAY_IP --exit {resolved.ip}")
        return

    relay_name = prompt("Relay name (optional, e.g. ru-moscow)", default="")

    from meridian.commands.relay import run_deploy

    run_deploy(
        relay_ip=relay_ip,
        exit_arg=resolved.ip,
        user="root",
        relay_name=relay_name,
        listen_port=443,
        yes=False,
    )
