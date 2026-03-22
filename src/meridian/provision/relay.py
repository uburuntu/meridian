"""Relay node provisioner — deploys Realm TCP relay via SSH.

A relay node is a lightweight TCP forwarder (no Docker, no 3x-ui, no panel).
It runs Realm to forward port 443 to an exit server, preserving end-to-end
VLESS+Reality encryption between the client and the exit.
"""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass

from rich.console import Console
from rich.status import Status

from meridian.config import (
    REALM_GITHUB_URL,
    REALM_VERSION,
    RELAY_CONFIG_PATH,
    RELAY_SERVICE_NAME,
)
from meridian.provision.steps import StepResult
from meridian.ssh import ServerConnection

# Minimal packages needed on a relay node
_RELAY_PACKAGES = ["curl", "wget", "ufw", "ca-certificates"]

# BBR sysctl settings (same as common.py)
_BBR_SETTINGS = {
    "net.core.default_qdisc": "fq",
    "net.ipv4.tcp_congestion_control": "bbr",
}

# Realm systemd service template
_SYSTEMD_UNIT = """\
[Unit]
Description=Meridian Relay (Realm TCP forwarder)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/realm -c {config_path}
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""


@dataclass
class RelayContext:
    """Configuration for relay node provisioning."""

    relay_ip: str
    exit_ip: str
    exit_port: int = 443
    listen_port: int = 443
    user: str = "root"
    realm_version: str = REALM_VERSION


# ---------------------------------------------------------------------------
# Relay provisioning steps
# ---------------------------------------------------------------------------


class InstallRelayPackages:
    """Install minimal system packages on relay node."""

    name = "Install relay packages"

    def run(self, conn: ServerConnection, ctx: RelayContext) -> StepResult:
        check_cmd = "dpkg-query -W -f='${Package}\\n' " + " ".join(_RELAY_PACKAGES) + " 2>/dev/null"
        result = conn.run(check_cmd, timeout=15)
        installed = set(result.stdout.strip().splitlines()) if result.returncode == 0 else set()

        missing = [p for p in _RELAY_PACKAGES if p not in installed]
        if not missing:
            return StepResult(name=self.name, status="ok", detail="all packages present")

        update = conn.run("DEBIAN_FRONTEND=noninteractive apt-get update -qq", timeout=120)
        if update.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"apt-get update failed: {update.stderr.strip()[:200]}",
            )

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

        return StepResult(name=self.name, status="changed", detail=f"installed {len(missing)} packages")


class ConfigureRelayBBR:
    """Enable BBR congestion control on relay node."""

    name = "Enable BBR congestion control"

    def run(self, conn: ServerConnection, ctx: RelayContext) -> StepResult:
        check = conn.run("sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null", timeout=10)
        if check.returncode == 0 and check.stdout.strip() == "bbr":
            qdisc = conn.run("sysctl -n net.core.default_qdisc 2>/dev/null", timeout=10)
            if qdisc.returncode == 0 and qdisc.stdout.strip() == "fq":
                return StepResult(name=self.name, status="ok", detail="already enabled")

        for key, value in _BBR_SETTINGS.items():
            result = conn.run(f"sysctl -w {key}={value}", timeout=10)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"sysctl {key} failed: {result.stderr.strip()[:200]}",
                )

        for key, value in _BBR_SETTINGS.items():
            conn.run(f"sed -i '/^{key}/d' /etc/sysctl.conf", timeout=10)
            conn.run(f"echo '{key} = {value}' >> /etc/sysctl.conf", timeout=10)

        return StepResult(name=self.name, status="changed")


class ConfigureRelayFirewall:
    """Configure UFW firewall on relay node."""

    name = "Configure relay firewall"

    def run(self, conn: ServerConnection, ctx: RelayContext) -> StepResult:
        check = conn.run("which ufw", timeout=5)
        if check.returncode != 0:
            return StepResult(name=self.name, status="failed", detail="ufw not found")

        changed = False

        ufw_status = conn.run("ufw status", timeout=10)
        ufw_active = ufw_status.returncode == 0 and "Status: active" in ufw_status.stdout

        # Allow SSH
        result = conn.run("ufw allow 22/tcp", timeout=10)
        if result.returncode != 0:
            return StepResult(name=self.name, status="failed", detail="failed to allow SSH")
        if "Skipping" not in result.stdout:
            changed = True

        # Allow relay port
        result = conn.run(f"ufw allow {ctx.listen_port}/tcp", timeout=10)
        if result.returncode != 0:
            return StepResult(name=self.name, status="failed", detail="failed to allow relay port")
        if "Skipping" not in result.stdout:
            changed = True

        conn.run("ufw default deny incoming", timeout=10)
        conn.run("ufw default allow outgoing", timeout=10)

        if not ufw_active:
            result = conn.run("echo y | ufw enable", timeout=15)
            if result.returncode != 0:
                return StepResult(name=self.name, status="failed", detail="ufw enable failed")
            changed = True
        else:
            conn.run("ufw reload", timeout=15)

        return StepResult(name=self.name, status="changed" if changed else "ok")


class InstallRealm:
    """Download and install Realm binary from GitHub releases."""

    name = "Install Realm TCP relay"

    def run(self, conn: ServerConnection, ctx: RelayContext) -> StepResult:
        # Check if Realm is already installed at the right version
        check = conn.run("realm --version 2>/dev/null", timeout=10)
        if check.returncode == 0:
            installed_version = check.stdout.strip()
            if ctx.realm_version in installed_version:
                return StepResult(name=self.name, status="ok", detail=f"v{ctx.realm_version} already installed")

        # Detect architecture
        arch_result = conn.run("uname -m", timeout=5)
        if arch_result.returncode != 0:
            return StepResult(name=self.name, status="failed", detail="cannot detect architecture")

        arch = arch_result.stdout.strip()
        if arch == "x86_64":
            target = "x86_64-unknown-linux-gnu"
        elif arch in ("aarch64", "arm64"):
            target = "aarch64-unknown-linux-gnu"
        else:
            return StepResult(name=self.name, status="failed", detail=f"unsupported arch: {arch}")

        # Download Realm binary
        q_version = shlex.quote(ctx.realm_version)
        q_target = shlex.quote(target)
        url = f"{REALM_GITHUB_URL}/v{q_version}/realm-{q_target}.tar.gz"
        q_url = shlex.quote(url)

        download = conn.run(
            f"curl -fsSL {q_url} -o /tmp/realm.tar.gz",
            timeout=60,
        )
        if download.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"download failed: {download.stderr.strip()[:200]}",
            )

        # Extract and install
        extract = conn.run(
            "tar xzf /tmp/realm.tar.gz -C /tmp && "
            "install -m 755 /tmp/realm /usr/local/bin/realm && "
            "rm -f /tmp/realm.tar.gz /tmp/realm",
            timeout=30,
        )
        if extract.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"extract/install failed: {extract.stderr.strip()[:200]}",
            )

        # Verify
        verify = conn.run("realm --version", timeout=10)
        if verify.returncode != 0:
            return StepResult(name=self.name, status="failed", detail="realm binary not working after install")

        return StepResult(name=self.name, status="changed", detail=f"installed v{ctx.realm_version}")


class ConfigureRealm:
    """Write Realm config and systemd service, then start."""

    name = "Configure Realm relay"

    def run(self, conn: ServerConnection, ctx: RelayContext) -> StepResult:
        q_exit_ip = shlex.quote(ctx.exit_ip)

        # Write Realm config
        config_content = (
            "[network]\n"
            "no_tcp = false\n"
            "use_udp = true\n"
            "\n"
            "[[endpoints]]\n"
            f'listen = "0.0.0.0:{ctx.listen_port}"\n'
            f'remote = "{ctx.exit_ip}:{ctx.exit_port}"\n'
        )

        conn.run("mkdir -p /etc/meridian", timeout=5)

        q_config = shlex.quote(config_content)
        write_config = conn.run(
            f"printf '%s' {q_config} > {RELAY_CONFIG_PATH}",
            timeout=10,
        )
        if write_config.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write config: {write_config.stderr.strip()[:200]}",
            )
        conn.run(f"chmod 644 {RELAY_CONFIG_PATH}", timeout=5)

        # Write relay metadata
        relay_meta = (
            "role: relay\n"
            f"exit_ip: {ctx.exit_ip}\n"
            f"exit_port: {ctx.exit_port}\n"
            f"listen_port: {ctx.listen_port}\n"
        )
        q_meta = shlex.quote(relay_meta)
        conn.run(f"printf '%s' {q_meta} > /etc/meridian/relay.yml", timeout=10)
        conn.run("chmod 600 /etc/meridian/relay.yml", timeout=5)

        # Write systemd service
        unit_content = _SYSTEMD_UNIT.format(config_path=RELAY_CONFIG_PATH)
        q_unit = shlex.quote(unit_content)
        service_path = f"/etc/systemd/system/{RELAY_SERVICE_NAME}.service"
        write_service = conn.run(f"printf '%s' {q_unit} > {service_path}", timeout=10)
        if write_service.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write service: {write_service.stderr.strip()[:200]}",
            )

        # Reload systemd, enable and (re)start service
        conn.run("systemctl daemon-reload", timeout=15)
        conn.run(f"systemctl enable {RELAY_SERVICE_NAME}", timeout=10)
        restart = conn.run(f"systemctl restart {RELAY_SERVICE_NAME}", timeout=15)
        if restart.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"service restart failed: {restart.stderr.strip()[:200]}",
            )

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"forwarding :{ctx.listen_port} -> {q_exit_ip}:{ctx.exit_port}",
        )


class VerifyRelay:
    """Verify Realm service is running and relay->exit connectivity works."""

    name = "Verify relay connectivity"

    def run(self, conn: ServerConnection, ctx: RelayContext) -> StepResult:
        # Check service is running
        status_result = conn.run(f"systemctl is-active {RELAY_SERVICE_NAME}", timeout=10)
        if status_result.returncode != 0 or status_result.stdout.strip() != "active":
            # Collect journal for diagnosis
            logs = conn.run(f"journalctl -u {RELAY_SERVICE_NAME} --no-pager -n 10", timeout=10)
            detail = logs.stdout.strip()[-200:] if logs.returncode == 0 else "service not active"
            return StepResult(name=self.name, status="failed", detail=detail)

        # Test TCP connectivity from relay to exit
        q_exit_ip = shlex.quote(ctx.exit_ip)
        tcp_test = conn.run(
            f"bash -c 'echo > /dev/tcp/{q_exit_ip}/{ctx.exit_port}' 2>/dev/null",
            timeout=10,
        )
        if tcp_test.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"relay cannot reach exit {ctx.exit_ip}:{ctx.exit_port}",
            )

        return StepResult(name=self.name, status="ok", detail="service active, exit reachable")


# ---------------------------------------------------------------------------
# Pipeline builder
# ---------------------------------------------------------------------------


def build_relay_steps(ctx: RelayContext) -> list:
    """Assemble the relay deployment step pipeline."""
    return [
        InstallRelayPackages(),
        ConfigureRelayBBR(),
        ConfigureRelayFirewall(),
        InstallRealm(),
        ConfigureRealm(),
        VerifyRelay(),
    ]


def run_relay_pipeline(conn: ServerConnection, ctx: RelayContext) -> list[StepResult]:
    """Execute relay provisioning steps with Rich progress output."""
    console = Console(stderr=True, highlight=False)
    steps = build_relay_steps(ctx)
    results: list[StepResult] = []

    total = len(steps)
    for i, step in enumerate(steps):
        start = time.monotonic()
        prefix = f"[{i + 1}/{total}]"
        with Status(f"  [cyan]{prefix} {step.name}[/cyan]", console=console, spinner="dots"):
            result = step.run(conn, ctx)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        results.append(result)

        if result.status == "failed":
            detail = f" ({result.detail})" if result.detail else ""
            console.print(f"  [red bold]\u2717[/red bold] {result.name}{detail}")
            break
        elif result.status == "skipped":
            detail = f" ({result.detail})" if result.detail else ""
            console.print(f"  [dim]\u2013 {result.name}{detail}[/dim]")
        else:
            detail = f" [dim]({result.detail})[/dim]" if result.detail else ""
            console.print(f"  [green]\u2713[/green] {result.name}{detail}")

    return results
