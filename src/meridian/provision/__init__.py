"""Provisioning engine — deploys and configures proxy servers via SSH.

The build_setup_steps() function assembles the full deployment pipeline:
  common -> docker -> xray (panel + inbounds) -> nginx -> connection page
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
    4. nginx: SNI routing + TLS + web serving (domain mode or hosted page)
    5. connection page: QR codes, stats, HTML (domain mode or hosted page)
    """
    from meridian.provision.common import (
        CheckDiskSpace,
        ConfigureBBR,
        ConfigureFirewall,
        EnableAutoUpgrades,
        EnsurePort443,
        HardenSSH,
        InstallPackages,
        SetTimezone,
    )
    from meridian.provision.docker import Deploy3xui, InstallDocker
    from meridian.provision.panel import ConfigurePanel, LoginToPanel
    from meridian.provision.xray import (
        CreateInbound,
        DisableXrayLogs,
        VerifyXray,
    )

    first_client = ctx.get("first_client_name", "default") or "default"
    creds_path = Path(ctx.creds_dir) / "proxy.yml"

    steps: list[Step] = [
        # -- Pre-flight --
        CheckDiskSpace(),
        # -- Common (OS-level setup) --
        InstallPackages(),
        EnableAutoUpgrades(),
        SetTimezone(),
    ]

    # Server hardening (optional — skip for shared servers with existing services)
    if ctx.harden:
        steps.append(HardenSSH())

    steps.extend(
        [
            ConfigureBBR(),
        ]
    )

    if ctx.harden:
        steps.append(ConfigureFirewall())
    else:
        # Even without --harden, ensure port 443 is allowed if ufw is active.
        # Without this, a pre-existing firewall blocks the deployment.
        steps.append(EnsurePort443())

    steps.extend(
        [
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
            CreateInbound(
                protocol_key="reality",
                port=ctx.reality_port,
                first_client_name=first_client,
                listen="127.0.0.1" if ctx.needs_web_server else "",
                delete_on_port_mismatch=True,
            ),
        ]
    )

    # XHTTP inbound (enabled by default)
    if ctx.xhttp_enabled:
        steps.append(
            CreateInbound(
                protocol_key="xhttp",
                port=ctx.xhttp_port,
                listen="127.0.0.1",
                ctx_exports={"xhttp_port": "port"},
            )
        )

    # Domain mode: WSS inbound
    if ctx.domain_mode:
        steps.append(
            CreateInbound(
                protocol_key="wss",
                port=ctx.wss_port,
                listen="127.0.0.1",
            )
        )

    steps.append(DisableXrayLogs())
    steps.append(VerifyXray())

    # nginx + connection page (domain mode or hosted page)
    if ctx.needs_web_server:
        from meridian.provision.services import (
            DeployConnectionPage,
            DeployPWAAssets,
            InstallNginx,
        )

        if ctx.domain_mode:
            steps.append(InstallNginx(domain=ctx.domain, reality_backend_port=ctx.reality_port))
        else:
            steps.append(
                InstallNginx(
                    domain="",
                    ip_mode=True,
                    server_ip=ctx.ip,
                    reality_backend_port=ctx.reality_port,
                )
            )

        steps.append(DeployPWAAssets())
        steps.append(DeployConnectionPage(server_ip=ctx.ip))

    return steps
