"""Provisioning engine — deploys and configures proxy servers via SSH.

The build_setup_steps() function assembles the full deployment pipeline:
  common -> docker -> xray (panel + inbounds) -> haproxy -> caddy -> output
"""

from __future__ import annotations

from pathlib import Path

from meridian.provision.steps import ProvisionContext, Provisioner, Step, StepResult

__all__ = ["Provisioner", "ProvisionContext", "Step", "StepResult", "build_setup_steps"]


def build_setup_steps(ctx: ProvisionContext) -> list[Step]:
    """Assemble the full deployment step pipeline.

    Execution order:
    1. common: packages, hardening, sysctl, firewall
    2. docker: install Docker, deploy 3x-ui container
    3. xray: configure panel, login, create inbounds, verify
    4. haproxy: SNI router (domain mode only)
    5. caddy: TLS + connection page (domain mode only)
    """
    from meridian.provision.common import (
        ConfigureBBR,
        ConfigureFirewall,
        EnableAutoUpgrades,
        HardenSSH,
        InstallPackages,
        SetTimezone,
    )
    from meridian.provision.docker import Deploy3xui, InstallDocker
    from meridian.provision.panel import ConfigurePanel, LoginToPanel
    from meridian.provision.xray import (
        CreateRealityInbound,
        CreateWSSInbound,
        CreateXHTTPInbound,
        VerifyXray,
    )

    first_client = ctx.get("first_client_name", "default") or "default"
    creds_path = Path(ctx.creds_dir) / "proxy.yml"

    steps: list[Step] = [
        # -- Common (OS-level setup) --
        InstallPackages(),
        EnableAutoUpgrades(),
        SetTimezone(),
        HardenSSH(),
        ConfigureBBR(),
        ConfigureFirewall(),
        # -- Docker --
        InstallDocker(),
        Deploy3xui(),
        # -- Panel + Xray --
        ConfigurePanel(
            creds_path=creds_path,
            server_ip=ctx.ip,
            domain=ctx.domain,
            sni=ctx.sni,
            first_client_name=first_client,
            panel_port=ctx.panel_port,
            xhttp_enabled=ctx.xhttp_enabled,
        ),
        LoginToPanel(),
        CreateRealityInbound(port=ctx.reality_port, first_client_name=first_client),
    ]

    # XHTTP inbound (enabled by default)
    if ctx.xhttp_enabled:
        steps.append(CreateXHTTPInbound(port=ctx.xhttp_port))

    # Domain mode: WSS inbound
    if ctx.domain_mode:
        steps.append(CreateWSSInbound(port=0))  # WSS binds to 127.0.0.1

    steps.append(VerifyXray())

    # Domain mode: HAProxy + Caddy
    if ctx.domain_mode:
        from meridian.provision.services import InstallCaddy, InstallHAProxy

        steps.append(InstallHAProxy(reality_sni=ctx.sni))
        steps.append(InstallCaddy(domain=ctx.domain))

    return steps
