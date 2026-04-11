"""Cluster recovery -- reconstruct cluster.yml from a running panel.

When local state is lost (new machine, accidental deletion), this command
rebuilds cluster.yml by querying the Remnawave panel API. The panel
database is the source of truth for nodes, inbounds, and config profiles.
"""

from __future__ import annotations

from meridian.cluster import (
    ClusterConfig,
    InboundRef,
    NodeEntry,
    PanelConfig,
)
from meridian.console import err_console, fail, info, ok, warn
from meridian.remnawave import MeridianPanel, RemnawaveError


# -- Recovery --


def run_recover(panel_url: str, api_token: str) -> None:
    """Reconstruct cluster.yml from a running Remnawave panel."""
    if not panel_url:
        fail(
            "Panel URL is required",
            hint="Usage: meridian recover https://panel.example.com TOKEN",
            hint_type="user",
        )
    if not api_token:
        fail(
            "API token is required",
            hint="Usage: meridian recover PANEL_URL TOKEN",
            hint_type="user",
        )

    # Normalize URL
    panel_url = panel_url.rstrip("/")

    info(f"Connecting to panel at {panel_url}...")

    panel = MeridianPanel(panel_url, api_token)
    with panel:
        # Verify connectivity
        if not panel.ping():
            fail(
                f"Cannot reach panel at {panel_url}",
                hint="Check the URL and API token. Try: curl " + panel_url + "/api/health",
                hint_type="user",
            )
        ok("Panel is reachable")

        # Fetch nodes
        try:
            api_nodes = panel.list_nodes()
        except RemnawaveError as e:
            fail(f"Could not fetch nodes: {e}", hint=e.hint, hint_type=e.hint_type)

        info(f"Found {len(api_nodes)} node(s)")

        # Fetch config profiles
        config_profile_uuid = ""
        config_profile_name = ""
        try:
            profiles = panel.list_config_profiles()
            if profiles:
                # Use the first profile as the active one
                config_profile_uuid = profiles[0].uuid
                config_profile_name = profiles[0].name
                info(f"Config profile: {config_profile_name}")
        except RemnawaveError:
            warn("Could not fetch config profiles")

        # Fetch inbounds
        inbounds: dict[str, InboundRef] = {}
        try:
            api_inbounds = panel.list_inbounds()
            for ib in api_inbounds:
                if ib.tag:
                    inbounds[ib.tag] = InboundRef(uuid=ib.uuid, tag=ib.tag)
            info(f"Found {len(inbounds)} inbound(s)")
        except RemnawaveError:
            warn("Could not fetch inbounds")

    # Reconstruct nodes
    nodes: list[NodeEntry] = []
    for i, api_node in enumerate(api_nodes):
        node = NodeEntry(
            ip=api_node.address,
            uuid=api_node.uuid,
            name=api_node.name,
            is_panel_host=(i == 0),  # assume first node is panel host
        )
        nodes.append(node)

    # Build cluster config
    cluster = ClusterConfig(
        version=1,
        panel=PanelConfig(
            url=panel_url,
            api_token=api_token,
        ),
        config_profile_uuid=config_profile_uuid,
        config_profile_name=config_profile_name,
        nodes=nodes,
        inbounds=inbounds,
    )

    cluster.save()
    ok("Cluster config saved to ~/.meridian/cluster.yml")

    # Print summary
    err_console.print()
    err_console.print("  [bold]Recovered cluster[/bold]")
    err_console.print(f"    Panel:     {panel_url}")
    err_console.print(f"    Nodes:     {len(nodes)}")
    for node in nodes:
        role = " (panel)" if node.is_panel_host else ""
        err_console.print(f"      {node.ip}  {node.name}{role}")
    err_console.print(f"    Inbounds:  {len(inbounds)}")
    if config_profile_name:
        err_console.print(f"    Profile:   {config_profile_name}")

    err_console.print()
    warn("Review ~/.meridian/cluster.yml -- some fields (SSH user, SNI, relays) need manual setup")
    err_console.print()
    err_console.print("  [dim]Fleet status:   meridian fleet status[/dim]")
    err_console.print("  [dim]List nodes:     meridian node list[/dim]")
    err_console.print("  [dim]List clients:   meridian client list[/dim]")
    err_console.print()
