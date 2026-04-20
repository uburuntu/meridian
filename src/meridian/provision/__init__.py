"""Provisioning engine — deploys and configures proxy servers via SSH.

The build_setup_steps() function assembles the full deployment pipeline:
  common -> docker -> remnawave (panel + node) -> nginx -> connection page

4.0: Replaces 3x-ui with Remnawave panel/node architecture.
"""

from __future__ import annotations

from meridian.provision.steps import ProvisionContext, Provisioner, Step, StepContext, StepResult

__all__ = ["Provisioner", "ProvisionContext", "Step", "StepContext", "StepResult", "build_setup_steps"]


def build_setup_steps(ctx: ProvisionContext) -> list[Step]:
    """Assemble the full deployment step pipeline.

    Execution order:
    1. common: packages, hardening, sysctl, firewall
    2. docker: install Docker
    3. remnawave: panel (if is_panel_host) + node containers
    4. nginx: SNI routing + TLS + web serving
    5. connection page: PWA assets (if hosted page)
    """
    from meridian.provision.common import (
        REQUIRED_PACKAGES,
        CheckDiskSpace,
        ConfigureBBR,
        ConfigureFail2ban,
        ConfigureFirewall,
        EnableAutoUpgrades,
        EnsurePort443,
        HardenSSH,
        InstallPackages,
        SetTimezone,
    )
    from meridian.provision.docker import InstallDocker
    from meridian.provision.remnawave_panel import DeployRemnawavePanel

    # Python operator precedence on `+` vs `if-else` is a trap here:
    # `A + B if cond else None` parses as `(A + B) if cond else None`,
    # which silently yields `InstallPackages(None)` when not hardening —
    # meaning REQUIRED_PACKAGES never get installed at all. Explicit form:
    extra_pkgs = ["fail2ban"] if ctx.harden else []

    steps: list[Step] = [
        # -- Pre-flight --
        CheckDiskSpace(),
        # -- Common (OS-level setup) --
        InstallPackages(REQUIRED_PACKAGES + extra_pkgs),
        EnableAutoUpgrades(),
        SetTimezone(),
    ]

    # Server hardening (optional — skip for shared servers with existing services)
    if ctx.harden:
        steps.append(HardenSSH())
        steps.append(ConfigureFail2ban())

    steps.append(ConfigureBBR())

    if ctx.harden:
        steps.append(ConfigureFirewall())
    else:
        # Even without --harden, ensure port 443 is allowed if ufw is active.
        steps.append(EnsurePort443())

    # -- Docker --
    steps.append(InstallDocker())

    # -- Remove legacy 3x-ui if present (v3 → v4 upgrade) --
    from meridian.provision.legacy_cleanup import CleanupLegacyPanel

    steps.append(CleanupLegacyPanel())

    # -- Remnawave panel (node deployed after API setup, not here) --
    if ctx.is_panel_host:
        steps.append(DeployRemnawavePanel())

    # Note: DeployRemnawaveNode is NOT included here because it requires
    # the node_secret_key from the panel API. The node is deployed in the
    # post-provisioner phase (setup.py _configure_panel_and_node) after
    # the panel is up and the node has been registered via REST API.

    # -- WARP client (optional) --
    if ctx.warp:
        from meridian.provision.warp import InstallWarp

        steps.append(InstallWarp())

    # -- nginx + TLS + connection page --
    if ctx.needs_web_server:
        from meridian.provision.nginx import ConfigureNginx, InstallNginx
        from meridian.provision.tls import IssueTLSCert

        steps.append(InstallNginx())

        if ctx.domain_mode:
            steps.append(ConfigureNginx(domain=ctx.domain, reality_backend_port=ctx.reality_port))
            steps.append(IssueTLSCert(domain=ctx.domain))
        else:
            steps.append(
                ConfigureNginx(
                    domain="",
                    ip_mode=True,
                    server_ip=ctx.ip,
                    reality_backend_port=ctx.reality_port,
                )
            )
            steps.append(IssueTLSCert(domain="", ip_mode=True, server_ip=ctx.ip))

        # PWA assets (connection pages deployed via post-provisioner API setup)
        from meridian.provision.services import DeployPWAAssets

        steps.append(DeployPWAAssets())

    return steps


def build_node_steps(ctx: ProvisionContext) -> list[Step]:
    """Assemble the pipeline for adding a node-only server (no panel).

    Used by `meridian node add <IP>`.
    """
    from meridian.provision.common import (
        REQUIRED_PACKAGES,
        CheckDiskSpace,
        ConfigureBBR,
        ConfigureFail2ban,
        ConfigureFirewall,
        EnableAutoUpgrades,
        EnsurePort443,
        HardenSSH,
        InstallPackages,
        SetTimezone,
    )
    from meridian.provision.docker import InstallDocker

    extra_pkgs = ["fail2ban"] if ctx.harden else []

    steps: list[Step] = [
        CheckDiskSpace(),
        InstallPackages(REQUIRED_PACKAGES + extra_pkgs),
        EnableAutoUpgrades(),
        SetTimezone(),
    ]

    if ctx.harden:
        steps.append(HardenSSH())
        # Mirror `build_setup_steps` — without this, redeploys (which take
        # the node-only path because `is_panel_host=is_first_deploy`) never
        # configure fail2ban even when the operator asked for hardening.
        steps.append(ConfigureFail2ban())

    steps.append(ConfigureBBR())

    if ctx.harden:
        steps.append(ConfigureFirewall())
    else:
        steps.append(EnsurePort443())

    steps.extend(
        [
            InstallDocker(),
            # Node deployed after API setup (setup.py), not in pipeline
        ]
    )

    if ctx.needs_web_server:
        from meridian.provision.nginx import ConfigureNginx, InstallNginx
        from meridian.provision.tls import IssueTLSCert

        steps.append(InstallNginx())

        if ctx.domain_mode:
            steps.append(ConfigureNginx(domain=ctx.domain, reality_backend_port=ctx.reality_port))
            steps.append(IssueTLSCert(domain=ctx.domain))
        else:
            steps.append(
                ConfigureNginx(
                    domain="",
                    ip_mode=True,
                    server_ip=ctx.ip,
                    reality_backend_port=ctx.reality_port,
                )
            )
            steps.append(IssueTLSCert(domain="", ip_mode=True, server_ip=ctx.ip))

    return steps
