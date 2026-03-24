"""Uninstall provisioning steps.

Replaces playbook-uninstall.yml. Removes proxy components but leaves
Docker engine and system packages intact.
"""

from __future__ import annotations

from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection


class Uninstall:
    """Remove all Meridian proxy components from the server.

    Removes: 3x-ui container+image, /opt/3x-ui, HAProxy config,
    Caddy Meridian config, web files, cron jobs, server credentials,
    CLI symlink, UFW rules.

    Does NOT remove: Docker engine, system packages, SSH settings.
    """

    name = "Uninstall Meridian"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        commands = [
            # 3x-ui container and data
            "cd /opt/3x-ui && docker compose down --rmi all 2>/dev/null; true",
            "rm -rf /opt/3x-ui",
            # HAProxy (+ systemd restart override)
            "systemctl stop haproxy 2>/dev/null; systemctl disable haproxy 2>/dev/null; true",
            "rm -f /etc/haproxy/haproxy.cfg",
            "rm -rf /etc/systemd/system/haproxy.service.d",
            # Caddy (+ systemd restart override)
            "systemctl stop caddy 2>/dev/null; systemctl disable caddy 2>/dev/null; true",
            "rm -f /etc/caddy/conf.d/meridian.caddy",
            "rm -rf /etc/systemd/system/caddy.service.d",
            "rm -rf /var/www/private",
            # Cron jobs (stats + health watchdog)
            (
                "crontab -l 2>/dev/null"
                " | grep -v 'update-stats.py'"
                " | grep -v 'health-check.sh'"
                " | crontab - 2>/dev/null; true"
            ),
            # Server credentials and scripts
            "rm -rf /etc/meridian /root/meridian",
            # CLI symlink
            "rm -f /usr/local/bin/meridian",
            # Systemd daemon-reload after removing overrides
            "systemctl daemon-reload 2>/dev/null; true",
            # UFW rules
            "ufw delete allow 443/tcp 2>/dev/null; true",
            "ufw delete allow 80/tcp 2>/dev/null; true",
        ]

        # XHTTP port cleanup
        if ctx.xhttp_port:
            commands.append(f"ufw delete allow {ctx.xhttp_port}/tcp 2>/dev/null; true")

        errors = []
        for cmd in commands:
            result = conn.run(cmd, timeout=30)
            if result.returncode != 0 and "true" not in cmd:
                errors.append(f"{cmd}: {result.stderr.strip()[:100]}")

        if errors:
            return StepResult(
                name=self.name,
                status="failed",
                detail="; ".join(errors[:3]),
            )

        return StepResult(name=self.name, status="changed", detail="all components removed")
