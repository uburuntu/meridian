"""OS-level provisioning steps: packages, hardening, firewall, sysctl."""

from __future__ import annotations

import shlex

from meridian.provision.steps import ProvisionContext, StepContext, StepResult
from meridian.ssh import ServerConnection

# Minimum disk space required (in MB)
MIN_DISK_SPACE_MB = 2048

# Packages required by the deployment stack
REQUIRED_PACKAGES = [
    "curl",
    "cron",
    "socat",
    "wget",
    "unzip",
    "jq",
    "ufw",
    "gnupg",
    "apt-transport-https",
    "ca-certificates",
    "python3-pip",
    "unattended-upgrades",
    "apt-listchanges",
    "dnsutils",
]

# Auto-upgrades config content
_AUTO_UPGRADES_CONF = """\
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
"""

# BBR sysctl settings
_BBR_SETTINGS = {
    "net.core.default_qdisc": "fq",
    "net.ipv4.tcp_congestion_control": "bbr",
}

_SSH_HARDENING_DROPIN_PATH = "/etc/ssh/sshd_config.d/00-meridian.conf"
_SSH_HARDENING_DROPIN_OLD_PATH = "/etc/ssh/sshd_config.d/99-meridian.conf"
_SSH_HARDENING_DROPIN = """\
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
DebianBanner no
"""


def _parse_ssh_ports(output: str) -> list[int]:
    """Parse one or more SSH ports from command output."""
    ports: list[int] = []
    seen: set[int] = set()

    for line in output.splitlines():
        for token in line.replace(",", " ").split():
            if not token.isdigit():
                continue
            port = int(token)
            if not (1 <= port <= 65535) or port in seen:
                continue
            seen.add(port)
            ports.append(port)
            break

    return ports


def detect_ssh_ports(conn: ServerConnection) -> list[int]:
    """Detect effective sshd listen ports, falling back to 22."""
    commands = [
        r"""sshd -T 2>/dev/null | awk '$1 == "port" {print $2}'""",
        (
            r"""grep -hEi '^[[:space:]]*Port[[:space:]]+[0-9]+' """
            r"""/etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null """
            r"""| awk '{print $2}'"""
        ),
    ]

    for command in commands:
        result = conn.run(command, timeout=15)
        if result.returncode != 0:
            continue
        ports = _parse_ssh_ports(result.stdout)
        if ports:
            return ports

    return [22]


class CheckDiskSpace:
    """Verify sufficient disk space before deployment."""

    name = "Check disk space"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        result = conn.run("df -BM --output=avail / | tail -1", timeout=15)
        if result.returncode != 0:
            return StepResult(name=self.name, status="skipped", detail="could not check disk space")

        try:
            avail_mb = int(result.stdout.strip().rstrip("M"))
        except (ValueError, AttributeError):
            return StepResult(name=self.name, status="skipped", detail="could not parse df output")

        if avail_mb < MIN_DISK_SPACE_MB:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"only {avail_mb}MB free, need {MIN_DISK_SPACE_MB}MB. Run: df -h",
            )

        return StepResult(name=self.name, status="ok", detail=f"{avail_mb}MB available")


class InstallPackages:
    """Install required system packages via apt."""

    name = "Install system packages"

    def __init__(self, packages: list[str] | None = None) -> None:
        self._packages = packages or REQUIRED_PACKAGES

    def run(self, conn: ServerConnection, ctx: StepContext) -> StepResult:
        # Check which packages are already installed
        check_cmd = "dpkg-query -W -f='${Package}\\n' " + " ".join(self._packages) + " 2>/dev/null"
        result = conn.run(check_cmd, timeout=15)
        installed = set(result.stdout.strip().splitlines()) if result.returncode == 0 else set()

        missing = [p for p in self._packages if p not in installed]
        if not missing:
            return StepResult(name=self.name, status="ok", detail="all packages present")

        # Update apt cache first
        update = conn.run("DEBIAN_FRONTEND=noninteractive apt-get update -qq", timeout=180)
        if update.returncode != 0:
            stderr = update.stderr.strip()
            if "no longer has a Release file" in stderr:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=(
                        "OS version is end-of-life — package repos have been removed. "
                        "Reinstall with an Ubuntu LTS version"
                    ),
                )
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"apt-get update failed: {stderr[:200]}",
            )

        # Install missing packages
        pkg_list = " ".join(missing)
        install = conn.run(
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {pkg_list}",
            timeout=300,
        )
        if install.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"apt-get install failed: {install.stderr.strip()[:200]}",
            )

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"installed {len(missing)} packages",
        )


class EnableAutoUpgrades:
    """Enable automatic security updates via unattended-upgrades."""

    name = "Enable automatic security updates"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        conf_path = "/etc/apt/apt.conf.d/20auto-upgrades"

        # Check if config already matches
        check = conn.run(f"cat {conf_path} 2>/dev/null", timeout=15)
        if check.returncode == 0 and check.stdout.strip() == _AUTO_UPGRADES_CONF.strip():
            return StepResult(name=self.name, status="ok", detail="already configured")

        # Write the config
        # Use heredoc to avoid shell quoting issues
        write_cmd = f"cat > {conf_path} << 'MERIDIAN_EOF'\n{_AUTO_UPGRADES_CONF}MERIDIAN_EOF"
        result = conn.run(write_cmd, timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write config: {result.stderr.strip()[:200]}",
            )
        conn.run(f"chmod 644 {conf_path}", timeout=15)

        return StepResult(name=self.name, status="changed")


class SetTimezone:
    """Set system timezone to UTC."""

    name = "Set timezone to UTC"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check current timezone
        tz_cmd = "timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null"
        check = conn.run(tz_cmd, timeout=15)
        if check.returncode == 0 and check.stdout.strip() == "UTC":
            return StepResult(name=self.name, status="ok", detail="already UTC")

        result = conn.run("timedatectl set-timezone UTC", timeout=15)
        if result.returncode != 0:
            # Fallback: write directly
            result = conn.run("ln -sf /usr/share/zoneinfo/UTC /etc/localtime", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=result.stderr.strip()[:200],
                )

        return StepResult(name=self.name, status="changed")


class HardenSSH:
    """Install an authoritative sshd drop-in and restart sshd."""

    name = "Harden SSH configuration"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        changed = False
        check = conn.run(f"cat {_SSH_HARDENING_DROPIN_PATH} 2>/dev/null", timeout=15)
        if check.returncode != 0 or check.stdout.strip() != _SSH_HARDENING_DROPIN.strip():
            write_cmd = (
                "mkdir -p /etc/ssh/sshd_config.d && "
                f"cat > {_SSH_HARDENING_DROPIN_PATH} << 'MERIDIAN_EOF'\n{_SSH_HARDENING_DROPIN}MERIDIAN_EOF"
            )
            result = conn.run(write_cmd, timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to write sshd hardening drop-in: {result.stderr.strip()[:200]}",
                )
            conn.run(f"chmod 644 {_SSH_HARDENING_DROPIN_PATH}", timeout=15)
            conn.run(f"rm -f {_SSH_HARDENING_DROPIN_OLD_PATH}", timeout=15)
            # Neutralize conflicting settings in other drop-ins (e.g., cloud-init)
            # so our values are authoritative regardless of load order.
            conn.run(
                "for f in /etc/ssh/sshd_config.d/*.conf; do "
                f'[ "$f" = "{_SSH_HARDENING_DROPIN_PATH}" ] && continue; '
                "sed -i -E "
                r"'s/^[[:space:]]*(PasswordAuthentication"
                r"|KbdInteractiveAuthentication"
                r"|ChallengeResponseAuthentication)"
                r"[[:space:]]/#\1 /' "
                '"$f" 2>/dev/null; done',
                timeout=15,
            )
            changed = True

        # Validate config before restarting
        validate = conn.run("sshd -t", timeout=15)
        if validate.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"sshd config validation failed: {validate.stderr.strip()[:200]}",
            )

        # Validate effective settings too — cloud-init drop-ins can override the main file.
        # DebianBanner is a Debian/Ubuntu-specific directive that some OpenSSH
        # builds don't recognize — sshd -T silently omits it.  We still write
        # it (harmless when unsupported), but skip verification when absent.
        _required = ("passwordauthentication no", "kbdinteractiveauthentication no")
        _optional = ("debianbanner no",)

        for setting in _required:
            effective = conn.run(f"sshd -T | grep -q '^{setting}$'", timeout=15)
            if effective.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"effective sshd setting mismatch: expected '{setting}'",
                )

        for setting in _optional:
            effective = conn.run(f"sshd -T | grep -qi '^{setting.split()[0]}'", timeout=15)
            if effective.returncode != 0:
                # sshd doesn't recognize this directive — skip verification
                continue
            check = conn.run(f"sshd -T | grep -q '^{setting}$'", timeout=15)
            if check.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"effective sshd setting mismatch: expected '{setting}'",
                )

        if not changed:
            return StepResult(name=self.name, status="ok", detail="already hardened")

        # Restart sshd (service is named "sshd" on some distros, "ssh" on others)
        restart = conn.run("systemctl restart sshd 2>/dev/null || systemctl restart ssh", timeout=15)
        if restart.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"sshd restart failed: {restart.stderr.strip()[:200]}",
            )

        return StepResult(name=self.name, status="changed")


class ConfigureFail2ban:
    """Enable fail2ban with sshd jail for brute-force protection.

    Assumes fail2ban is already installed by InstallPackages.
    """

    name = "Configure fail2ban"

    def run(self, conn: ServerConnection, ctx: StepContext) -> StepResult:
        active = conn.run("systemctl is-active fail2ban", timeout=15)
        if active.returncode == 0 and active.stdout.strip() == "active":
            return StepResult(name=self.name, status="ok", detail="already running")

        # Enable and start service
        enable = conn.run("systemctl enable fail2ban", timeout=15)
        if enable.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to enable fail2ban: {enable.stderr.strip()[:200]}",
            )
        start = conn.run("systemctl restart fail2ban", timeout=30)
        if start.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to start fail2ban: {start.stderr.strip()[:200]}",
            )

        return StepResult(name=self.name, status="changed", detail="enabled and started")


class ConfigureBBR:
    """Enable BBR congestion control via sysctl."""

    name = "Enable BBR congestion control"

    def run(self, conn: ServerConnection, ctx: StepContext) -> StepResult:
        # Check if BBR is already enabled
        check = conn.run("sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null", timeout=15)
        if check.returncode == 0 and check.stdout.strip() == "bbr":
            qdisc = conn.run("sysctl -n net.core.default_qdisc 2>/dev/null", timeout=15)
            if qdisc.returncode == 0 and qdisc.stdout.strip() == "fq":
                return StepResult(name=self.name, status="ok", detail="already enabled")

        # Apply sysctl settings
        for key, value in _BBR_SETTINGS.items():
            result = conn.run(f"sysctl -w {key}={value}", timeout=15)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                # Containers and old kernels lack these tunables — warn, don't block deploy
                if "No such file" in stderr or "does not exist" in stderr:
                    return StepResult(
                        name=self.name,
                        status="changed",
                        detail=f"WARNING: {key} unavailable (kernel may not support BBR)",
                    )
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"sysctl {key} failed: {stderr[:200]}",
                )

        # Persist to sysctl.conf
        for key, value in _BBR_SETTINGS.items():
            # Remove existing entries and append new ones
            q_key = shlex.quote(key)
            q_value = shlex.quote(value)
            conn.run(f"sed -i '/^{key}/d' /etc/sysctl.conf", timeout=15)
            conn.run(f"printf '%s = %s\\n' {q_key} {q_value} >> /etc/sysctl.conf", timeout=15)

        return StepResult(name=self.name, status="changed")


class EnsurePort443:
    """Ensure port 443 is allowed if ufw is already active.

    Used when --no-harden skips full firewall configuration. Without this,
    a pre-existing firewall blocks the deployment silently.
    """

    name = "Ensure port 443"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        check = conn.run("which ufw", timeout=15)
        if check.returncode != 0:
            return StepResult(name=self.name, status="ok", detail="ufw not installed")

        ufw_status = conn.run("ufw status", timeout=15)
        if ufw_status.returncode != 0 or "Status: active" not in ufw_status.stdout:
            return StepResult(name=self.name, status="ok", detail="ufw not active")

        result = conn.run("ufw allow 443/tcp", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to allow HTTPS: {result.stderr.strip()[:200]}",
            )

        if "Skipping" in result.stdout:
            return StepResult(name=self.name, status="ok", detail="already allowed")
        return StepResult(name=self.name, status="changed", detail="port 443 added to ufw")


class ConfigureFirewall:
    """Configure UFW firewall rules."""

    name = "Configure firewall"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check if ufw is available
        check = conn.run("which ufw 2>/dev/null", timeout=15)
        if check.returncode != 0:
            # ufw not found — try to install it explicitly
            conn.run("apt-get update -qq && apt-get install -y -qq ufw", timeout=120)
            recheck = conn.run("which ufw", timeout=15)
            if recheck.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail="ufw not available — install it manually: apt-get install ufw",
                )

        changed = False

        # Check if ufw is already active
        ufw_status = conn.run("ufw status", timeout=15)
        ufw_active = ufw_status.returncode == 0 and "Status: active" in ufw_status.stdout

        # Allow the live sshd port(s) instead of assuming 22.
        for ssh_port in detect_ssh_ports(conn):
            result = conn.run(f"ufw allow {ssh_port}/tcp", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to allow SSH port {ssh_port}: {result.stderr.strip()[:200]}",
                )
            if "Skipping" not in result.stdout:
                changed = True

        # Allow HTTPS (port 443)
        result = conn.run("ufw allow 443/tcp", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to allow HTTPS: {result.stderr.strip()[:200]}",
            )
        if "Skipping" not in result.stdout:
            changed = True

        # Domain mode or hosted page: allow port 80 for ACME challenges
        if ctx.needs_web_server:
            result = conn.run("ufw allow 80/tcp", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to allow HTTP: {result.stderr.strip()[:200]}",
                )
            if "Skipping" not in result.stdout:
                changed = True
        else:
            # Cleanup stale port 80 rule if switching from domain/hosted mode
            result = conn.run("ufw delete allow 80/tcp 2>/dev/null", timeout=15)
            if result.returncode == 0 and "Skipping" not in result.stdout and "Could not" not in result.stdout:
                changed = True

        # Do not delete arbitrary user-managed rules. Meridian only owns the
        # standard public ports it opens itself (22/80/443), so cleanup is
        # limited to the stale port-80 rule above when web serving is disabled.

        # Set default policies and enable
        result = conn.run("ufw default deny incoming", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"ufw default deny incoming failed: {result.stderr.strip()[:200]}",
            )
        result = conn.run("ufw default allow outgoing", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"ufw default allow outgoing failed: {result.stderr.strip()[:200]}",
            )

        # Enable ufw (non-interactive) -- only counts as changed if it wasn't active
        if not ufw_active:
            result = conn.run("echo y | ufw enable", timeout=30)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"ufw enable failed: {result.stderr.strip()[:200]}",
                )
            changed = True
        else:
            # Reload to apply any rule changes
            conn.run("ufw reload", timeout=30)

        return StepResult(
            name=self.name,
            status="changed" if changed else "ok",
        )
