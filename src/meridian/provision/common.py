"""OS-level provisioning steps: packages, hardening, firewall, sysctl."""

from __future__ import annotations

import shlex

from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# Minimum disk space required (in MB)
MIN_DISK_SPACE_MB = 2048

# Packages required by the deployment stack
REQUIRED_PACKAGES = [
    "curl",
    "socat",
    "wget",
    "unzip",
    "jq",
    "qrencode",
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


class CheckDiskSpace:
    """Verify sufficient disk space before deployment."""

    name = "Check disk space"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        result = conn.run("df -BM --output=avail / | tail -1", timeout=10)
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

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check which packages are already installed
        check_cmd = "dpkg-query -W -f='${Package}\\n' " + " ".join(REQUIRED_PACKAGES) + " 2>/dev/null"
        result = conn.run(check_cmd, timeout=15)
        installed = set(result.stdout.strip().splitlines()) if result.returncode == 0 else set()

        missing = [p for p in REQUIRED_PACKAGES if p not in installed]
        if not missing:
            return StepResult(name=self.name, status="ok", detail="all packages present")

        # Update apt cache first
        update = conn.run("DEBIAN_FRONTEND=noninteractive apt-get update -qq", timeout=120)
        if update.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"apt-get update failed: {update.stderr.strip()[:200]}",
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
        check = conn.run(f"cat {conf_path} 2>/dev/null", timeout=10)
        if check.returncode == 0 and check.stdout.strip() == _AUTO_UPGRADES_CONF.strip():
            return StepResult(name=self.name, status="ok", detail="already configured")

        # Write the config
        # Use heredoc to avoid shell quoting issues
        write_cmd = f"cat > {conf_path} << 'MERIDIAN_EOF'\n{_AUTO_UPGRADES_CONF}MERIDIAN_EOF"
        result = conn.run(write_cmd, timeout=10)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write config: {result.stderr.strip()[:200]}",
            )
        conn.run(f"chmod 644 {conf_path}", timeout=5)

        return StepResult(name=self.name, status="changed")


class SetTimezone:
    """Set system timezone to UTC."""

    name = "Set timezone to UTC"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check current timezone
        tz_cmd = "timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null"
        check = conn.run(tz_cmd, timeout=10)
        if check.returncode == 0 and check.stdout.strip() == "UTC":
            return StepResult(name=self.name, status="ok", detail="already UTC")

        result = conn.run("timedatectl set-timezone UTC", timeout=10)
        if result.returncode != 0:
            # Fallback: write directly
            result = conn.run("ln -sf /usr/share/zoneinfo/UTC /etc/localtime", timeout=10)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=result.stderr.strip()[:200],
                )

        return StepResult(name=self.name, status="changed")


class HardenSSH:
    """Disable SSH password authentication and restart sshd."""

    name = "Harden SSH configuration"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        changed = False

        # Disable PasswordAuthentication
        check_pa = conn.run("grep -qE '^PasswordAuthentication no$' /etc/ssh/sshd_config", timeout=10)
        if check_pa.returncode != 0:
            result = conn.run(
                "sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
                timeout=10,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to set PasswordAuthentication: {result.stderr.strip()[:200]}",
                )
            changed = True

        # Disable KbdInteractiveAuthentication (challenge-response)
        check_kbd = conn.run("grep -qE '^KbdInteractiveAuthentication no$' /etc/ssh/sshd_config", timeout=10)
        if check_kbd.returncode != 0:
            # Replace either ChallengeResponseAuthentication or KbdInteractiveAuthentication
            kbd_sed = (
                "sed -i "
                "'s/^#\\?ChallengeResponseAuthentication.*"
                "\\|^#\\?KbdInteractiveAuthentication.*"
                "/KbdInteractiveAuthentication no/' "
                "/etc/ssh/sshd_config"
            )
            result = conn.run(kbd_sed, timeout=10)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to set KbdInteractiveAuthentication: {result.stderr.strip()[:200]}",
                )
            changed = True

        # Strip OS version from SSH banner (DebianBanner appends distro info)
        check_banner = conn.run("grep -qE '^DebianBanner no$' /etc/ssh/sshd_config", timeout=10)
        if check_banner.returncode != 0:
            result = conn.run(
                "sed -i 's/^#\\?DebianBanner.*/DebianBanner no/' /etc/ssh/sshd_config",
                timeout=10,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to set DebianBanner: {result.stderr.strip()[:200]}",
                )
            # If sed matched nothing (no existing line), append it
            verify = conn.run("grep -qE '^DebianBanner no$' /etc/ssh/sshd_config", timeout=10)
            if verify.returncode != 0:
                conn.run("printf '\\nDebianBanner no\\n' >> /etc/ssh/sshd_config", timeout=10)
            changed = True

        if not changed:
            return StepResult(name=self.name, status="ok", detail="already hardened")

        # Validate config before restarting
        validate = conn.run("sshd -t", timeout=10)
        if validate.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"sshd config validation failed: {validate.stderr.strip()[:200]}",
            )

        # Restart sshd (service is named "sshd" on some distros, "ssh" on others)
        restart = conn.run("systemctl restart sshd 2>/dev/null || systemctl restart ssh", timeout=15)
        if restart.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"sshd restart failed: {restart.stderr.strip()[:200]}",
            )

        return StepResult(name=self.name, status="changed")


class ConfigureBBR:
    """Enable BBR congestion control via sysctl."""

    name = "Enable BBR congestion control"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check if BBR is already enabled
        check = conn.run("sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null", timeout=10)
        if check.returncode == 0 and check.stdout.strip() == "bbr":
            qdisc = conn.run("sysctl -n net.core.default_qdisc 2>/dev/null", timeout=10)
            if qdisc.returncode == 0 and qdisc.stdout.strip() == "fq":
                return StepResult(name=self.name, status="ok", detail="already enabled")

        # Apply sysctl settings
        for key, value in _BBR_SETTINGS.items():
            result = conn.run(f"sysctl -w {key}={value}", timeout=10)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"sysctl {key} failed: {result.stderr.strip()[:200]}",
                )

        # Persist to sysctl.conf
        for key, value in _BBR_SETTINGS.items():
            # Remove existing entries and append new ones
            q_key = shlex.quote(key)
            q_value = shlex.quote(value)
            conn.run(f"sed -i '/^{key}/d' /etc/sysctl.conf", timeout=10)
            conn.run(f"printf '%s = %s\\n' {q_key} {q_value} >> /etc/sysctl.conf", timeout=10)

        return StepResult(name=self.name, status="changed")


class ConfigureFirewall:
    """Configure UFW firewall rules."""

    name = "Configure firewall"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check if ufw is available
        check = conn.run("which ufw", timeout=5)
        if check.returncode != 0:
            return StepResult(name=self.name, status="failed", detail="ufw not found")

        changed = False

        # Check if ufw is already active
        ufw_status = conn.run("ufw status", timeout=10)
        ufw_active = ufw_status.returncode == 0 and "Status: active" in ufw_status.stdout

        # Allow SSH (port 22)
        result = conn.run("ufw allow 22/tcp", timeout=10)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to allow SSH: {result.stderr.strip()[:200]}",
            )
        if "Skipping" not in result.stdout:
            changed = True

        # Allow HTTPS (port 443)
        result = conn.run("ufw allow 443/tcp", timeout=10)
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
            result = conn.run("ufw allow 80/tcp", timeout=10)
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
            result = conn.run("ufw delete allow 80/tcp 2>/dev/null", timeout=10)
            if result.returncode == 0 and "Skipping" not in result.stdout and "Could not" not in result.stdout:
                changed = True

        # Clean up stale rules: delete any port that isn't in the allowed set.
        # Previous deploys or other tooling (3x-ui, Realm relays) may have
        # opened random high ports that are no longer needed.
        allowed_ports = {"22", "443"}
        if ctx.needs_web_server:
            allowed_ports.add("80")
        result = conn.run("ufw status", timeout=10)
        if result.returncode == 0:
            import re

            for line in result.stdout.splitlines():
                # Match lines like "8443/tcp    ALLOW IN    Anywhere"
                m = re.match(r"(\d+)/tcp\s+ALLOW", line.strip())
                if m and m.group(1) not in allowed_ports:
                    port = m.group(1)
                    conn.run(f"ufw delete allow {port}/tcp", timeout=10)
                    conn.run(f"ufw delete allow {port}/tcp", timeout=10)  # v6 rule
                    changed = True

        # Set default policies and enable
        conn.run("ufw default deny incoming", timeout=10)
        conn.run("ufw default allow outgoing", timeout=10)

        # Enable ufw (non-interactive) -- only counts as changed if it wasn't active
        if not ufw_active:
            result = conn.run("echo y | ufw enable", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"ufw enable failed: {result.stderr.strip()[:200]}",
                )
            changed = True
        else:
            # Reload to apply any rule changes
            conn.run("ufw reload", timeout=15)

        return StepResult(
            name=self.name,
            status="changed" if changed else "ok",
        )
