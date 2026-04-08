"""Tests for OS-level provisioning steps (common.py).

Each step is tested for idempotency: already-done returns "ok"/"skipped",
needs-change returns "changed", and failures return "failed".
"""

from __future__ import annotations

from meridian.provision.common import (
    _AUTO_UPGRADES_CONF,
    REQUIRED_PACKAGES,
    ConfigureBBR,
    ConfigureFail2ban,
    ConfigureFirewall,
    EnableAutoUpgrades,
    HardenSSH,
    InstallPackages,
    SetTimezone,
)
from tests.provision.conftest import MockConnection

# ---------------------------------------------------------------------------
# InstallPackages
# ---------------------------------------------------------------------------


class TestInstallPackages:
    def test_all_present_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When all packages are already installed, no apt-get install is called."""
        mock_conn.when("dpkg-query", stdout="\n".join(REQUIRED_PACKAGES) + "\n")

        result = InstallPackages().run(mock_conn, base_ctx)

        assert result.status == "ok"
        mock_conn.assert_not_called_with_pattern("apt-get install")

    def test_missing_packages_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When some packages are missing, apt-get install is called and status is changed."""
        # Return only a subset of required packages
        installed = REQUIRED_PACKAGES[:3]
        mock_conn.when("dpkg-query", stdout="\n".join(installed) + "\n")

        result = InstallPackages().run(mock_conn, base_ctx)

        assert result.status == "changed"
        mock_conn.assert_called_with_pattern("apt-get install")

    def test_apt_fails_returns_failed(self, mock_conn: MockConnection, base_ctx):
        """When apt-get install fails, status is failed."""
        mock_conn.when("dpkg-query", stdout="")
        mock_conn.when("apt-get install", rc=1, stderr="E: broken packages")

        result = InstallPackages().run(mock_conn, base_ctx)

        assert result.status == "failed"

    def test_eol_apt_update_gives_actionable_error(self, mock_conn: MockConnection, base_ctx):
        """When apt-get update fails with EOL Release file error, message suggests LTS."""
        mock_conn.when("dpkg-query", stdout="")
        mock_conn.when(
            "apt-get update",
            rc=1,
            stderr=(
                "E: The repository 'http://security.ubuntu.com/ubuntu oracular-security Release' "
                "no longer has a Release file."
            ),
        )

        result = InstallPackages().run(mock_conn, base_ctx)

        assert result.status == "failed"
        assert "end-of-life" in result.detail
        assert "Ubuntu LTS" in result.detail


# ---------------------------------------------------------------------------
# EnableAutoUpgrades
# ---------------------------------------------------------------------------


class TestEnableAutoUpgrades:
    def test_already_configured_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When config file already has expected content, nothing is written."""
        mock_conn.when("cat", stdout=_AUTO_UPGRADES_CONF.strip())

        result = EnableAutoUpgrades().run(mock_conn, base_ctx)

        assert result.status == "ok"

    def test_writes_config_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When config file is missing or empty, it is written."""
        mock_conn.when("cat /etc/apt", stdout="", rc=1)
        mock_conn.when("cat >", rc=0)

        result = EnableAutoUpgrades().run(mock_conn, base_ctx)

        assert result.status == "changed"


# ---------------------------------------------------------------------------
# SetTimezone
# ---------------------------------------------------------------------------


class TestSetTimezone:
    def test_already_utc_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When timezone is already UTC, no change is made."""
        mock_conn.when("timedatectl", stdout="UTC")

        result = SetTimezone().run(mock_conn, base_ctx)

        assert result.status == "ok"

    def test_changes_timezone_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When timezone differs, it is changed to UTC."""
        mock_conn.when("timedatectl show", stdout="America/New_York")
        mock_conn.when("timedatectl set-timezone", rc=0)

        result = SetTimezone().run(mock_conn, base_ctx)

        assert result.status == "changed"


# ---------------------------------------------------------------------------
# HardenSSH
# ---------------------------------------------------------------------------


class TestHardenSSH:
    def test_already_hardened_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When PasswordAuthentication and KbdInteractive are already off, status is ok."""
        # Both grep checks succeed (rc=0 means pattern found)
        mock_conn.when("grep", rc=0)

        result = HardenSSH().run(mock_conn, base_ctx)

        assert result.status == "ok"

    def test_hardens_ssh_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When password auth is enabled, SSH is hardened and sshd restarted."""
        # grep fails (pattern not found) -> needs hardening
        mock_conn.when("grep", rc=1)
        # sed, sshd -t, systemctl all succeed (default rc=0)

        result = HardenSSH().run(mock_conn, base_ctx)

        assert result.status == "changed"
        mock_conn.assert_called_with_pattern("systemctl restart sshd")

    def test_sshd_validation_fails_returns_failed(self, mock_conn: MockConnection, base_ctx):
        """When sshd -t validation fails, status is failed."""
        mock_conn.when("grep", rc=1)
        mock_conn.when("sshd -t", rc=1, stderr="sshd_config: bad configuration")

        result = HardenSSH().run(mock_conn, base_ctx)

        assert result.status == "failed"
        assert "validation failed" in result.detail


# ---------------------------------------------------------------------------
# ConfigureFail2ban
# ---------------------------------------------------------------------------


class TestConfigureFail2ban:
    def test_already_installed_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When fail2ban is already installed and running, status is ok."""
        mock_conn.when("which fail2ban-server", rc=0)
        mock_conn.when("systemctl enable fail2ban", rc=0)
        mock_conn.when("systemctl restart fail2ban", rc=0)

        result = ConfigureFail2ban().run(mock_conn, base_ctx)

        assert result.status == "ok"

    def test_installs_when_missing_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When fail2ban is not installed, it is installed and started."""
        mock_conn.when("which fail2ban-server", rc=1)
        mock_conn.when("apt-get install", rc=0)
        mock_conn.when("systemctl enable fail2ban", rc=0)
        mock_conn.when("systemctl restart fail2ban", rc=0)

        result = ConfigureFail2ban().run(mock_conn, base_ctx)

        assert result.status == "changed"
        mock_conn.assert_called_with_pattern("apt-get install")

    def test_install_failure_returns_failed(self, mock_conn: MockConnection, base_ctx):
        """When apt-get install fails, status is failed."""
        mock_conn.when("which fail2ban-server", rc=1)
        mock_conn.when("apt-get install", rc=1, stderr="E: Unable to locate package")

        result = ConfigureFail2ban().run(mock_conn, base_ctx)

        assert result.status == "failed"
        assert "apt-get install failed" in result.detail

    def test_service_start_failure_returns_failed(self, mock_conn: MockConnection, base_ctx):
        """When systemctl restart fails, status is failed."""
        mock_conn.when("which fail2ban-server", rc=0)
        mock_conn.when("systemctl enable fail2ban", rc=0)
        mock_conn.when("systemctl restart fail2ban", rc=1, stderr="Unit not found")

        result = ConfigureFail2ban().run(mock_conn, base_ctx)

        assert result.status == "failed"
        assert "failed to start" in result.detail


# ---------------------------------------------------------------------------
# ConfigureBBR
# ---------------------------------------------------------------------------


class TestConfigureBBR:
    def test_already_enabled_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When BBR and fq qdisc are already active, status is ok."""
        mock_conn.when("net.ipv4.tcp_congestion_control", stdout="bbr")
        mock_conn.when("net.core.default_qdisc", stdout="fq")

        result = ConfigureBBR().run(mock_conn, base_ctx)

        assert result.status == "ok"

    def test_enables_bbr_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When congestion control is cubic, BBR is enabled."""
        mock_conn.when("net.ipv4.tcp_congestion_control", stdout="cubic")

        result = ConfigureBBR().run(mock_conn, base_ctx)

        assert result.status == "changed"
        mock_conn.assert_called_with_pattern("sysctl -w")


# ---------------------------------------------------------------------------
# ConfigureFirewall
# ---------------------------------------------------------------------------


class TestConfigureFirewall:
    def test_ufw_not_found_returns_failed(self, mock_conn: MockConnection, base_ctx):
        """When ufw binary is not found and install fails, status is failed."""
        mock_conn.when("which ufw", rc=1)
        mock_conn.when("apt-get update", stdout="")
        mock_conn.when("apt-get install", stdout="")

        result = ConfigureFirewall().run(mock_conn, base_ctx)

        assert result.status == "failed"
        assert "ufw not available" in result.detail
        mock_conn.assert_called_with_pattern("apt-get install")

    def test_ufw_installed_after_retry(self, mock_conn: MockConnection, base_ctx):
        """When ufw is missing but apt install succeeds, step continues."""
        # First check (with 2>/dev/null) fails; recheck (without) succeeds
        mock_conn.when("which ufw 2>/dev/null", rc=1)
        mock_conn.when("which ufw", rc=0)
        mock_conn.when("apt-get update", stdout="")
        mock_conn.when("apt-get install", stdout="")
        mock_conn.when("ufw status", stdout="Status: inactive")
        mock_conn.when("ufw allow", stdout="Rule added")
        mock_conn.when("ufw delete", rc=0, stdout="Could not")
        mock_conn.when("ufw default", rc=0)
        mock_conn.when("ufw enable", stdout="Firewall is active")

        result = ConfigureFirewall().run(mock_conn, base_ctx)

        assert result.status == "changed"
        mock_conn.assert_called_with_pattern("apt-get install")

    def test_already_active_returns_ok(self, mock_conn: MockConnection, base_ctx):
        """When ufw is active and rules already exist, status is ok."""
        mock_conn.when("which ufw", rc=0)
        mock_conn.when("ufw status", stdout="Status: active\n22/tcp ALLOW\n443/tcp ALLOW")
        # All ufw allow commands return "Skipping" (rule exists)
        mock_conn.when("ufw allow", stdout="Skipping adding existing rule")
        mock_conn.when("ufw delete", rc=0, stdout="Skipping")
        mock_conn.when("ufw default", rc=0)
        mock_conn.when("ufw reload", rc=0)

        result = ConfigureFirewall().run(mock_conn, base_ctx)

        assert result.status == "ok"

    def test_enables_ufw_returns_changed(self, mock_conn: MockConnection, base_ctx):
        """When ufw is inactive, it is enabled and status is changed."""
        mock_conn.when("which ufw", rc=0)
        mock_conn.when("ufw status", stdout="Status: inactive")
        mock_conn.when("ufw allow", stdout="Rule added")
        mock_conn.when("ufw delete", rc=0, stdout="Could not")
        mock_conn.when("ufw default", rc=0)
        mock_conn.when("ufw enable", stdout="Firewall is active")

        result = ConfigureFirewall().run(mock_conn, base_ctx)

        assert result.status == "changed"

    def test_web_server_mode_allows_port_80(self, mock_conn: MockConnection, base_ctx):
        """When hosted_page is True, port 80 is opened for ACME challenges."""
        base_ctx.hosted_page = True

        mock_conn.when("which ufw", rc=0)
        mock_conn.when("ufw status", stdout="Status: active")
        mock_conn.when("ufw allow", stdout="Skipping adding existing rule")
        mock_conn.when("ufw default", rc=0)
        mock_conn.when("ufw reload", rc=0)

        ConfigureFirewall().run(mock_conn, base_ctx)

        mock_conn.assert_called_with_pattern("ufw allow 80/tcp")
