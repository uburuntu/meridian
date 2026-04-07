"""Docker and 3x-ui container provisioning steps."""

from __future__ import annotations

import shlex
import time

from meridian.panel import PanelError
from meridian.provision.panel import _wait_for_panel
from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# Services allowed on port 443 (our own stack components)
_PORT_443_ALLOWED = ("3x-ui", "xray", "nginx", "haproxy", "caddy")

# Conflicting Docker packages to remove before installing docker-ce
_CONFLICTING_PACKAGES = [
    "docker.io",
    "docker-compose",
    "docker-doc",
    "podman-docker",
    "containerd",
    "runc",
]


def _render_compose(ctx: ProvisionContext) -> str:
    """Render the docker-compose.yml for 3x-ui."""
    return f"""\
# 3x-ui Panel - Xray Management Interface
# Managed by Meridian. Manual edits will be overwritten on next run.
services:
  3x-ui:
    image: ghcr.io/mhsanaei/3x-ui:{ctx.threexui_version}
    container_name: 3x-ui
    restart: unless-stopped
    # Host networking required so Xray can bind to specific ports (443, etc.)
    network_mode: host
    volumes:
      - ./db/:/etc/x-ui/
      - ./cert/:/root/cert/
    environment:
      XRAY_VMESS_AEAD_FORCED: "true"
      XUI_ENABLE_FAIL2BAN: "true"
    tty: true
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
"""


class InstallDocker:
    """Install Docker CE from the official repository."""

    name = "Install Docker"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Check if Docker is already installed
        version_check = conn.run("docker --version", timeout=15)
        docker_installed = version_check.returncode == 0

        if docker_installed:
            # Ensure compose plugin is available (docker.io from distro
            # doesn't include it; docker-ce does but might be missing)
            compose_check = conn.run("docker compose version", timeout=15)
            if compose_check.returncode != 0:
                conn.run(
                    "DEBIAN_FRONTEND=noninteractive apt-get update -qq"
                    " && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq"
                    " docker-compose-plugin 2>/dev/null; true",
                    timeout=120,
                )
                # Verify it's now available
                recheck = conn.run("docker compose version", timeout=15)
                if recheck.returncode != 0:
                    return StepResult(
                        name=self.name,
                        status="failed",
                        detail=(
                            "docker compose plugin not available — "
                            "install docker-compose-plugin or upgrade to docker-ce"
                        ),
                    )

            # Check for running containers
            ps_check = conn.run("docker ps -q", timeout=15)
            has_containers = ps_check.returncode == 0 and ps_check.stdout.strip() != ""
            if has_containers:
                return StepResult(
                    name=self.name,
                    status="skipped",
                    detail="Docker running with containers",
                )

        # Check if docker-ce is specifically installed
        ce_check = conn.run("dpkg-query -W -f='${Status}' docker-ce 2>/dev/null", timeout=15)
        docker_ce_installed = ce_check.returncode == 0 and "install ok installed" in ce_check.stdout

        if docker_ce_installed:
            # Ensure Docker service is running
            conn.run("systemctl start docker", timeout=30)
            conn.run("systemctl enable docker", timeout=15)
            # Verify compose plugin (might be missing if manually removed)
            compose_check = conn.run("docker compose version", timeout=15)
            if compose_check.returncode != 0:
                conn.run(
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-compose-plugin 2>/dev/null; true",
                    timeout=120,
                )
            return StepResult(
                name=self.name,
                status="ok",
                detail="docker-ce already installed",
            )

        # Remove conflicting packages (only when docker-ce is NOT installed)
        if not docker_ce_installed:
            pkg_list = " ".join(_CONFLICTING_PACKAGES)
            conn.run(
                f"DEBIAN_FRONTEND=noninteractive apt-get remove -y {pkg_list} 2>/dev/null",
                timeout=120,
            )

        # Install prerequisites
        result = conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl gnupg",
            timeout=120,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"prerequisite install failed: {result.stderr.strip()[:200]}",
            )

        # Create keyrings directory
        conn.run("mkdir -p /etc/apt/keyrings && chmod 755 /etc/apt/keyrings", timeout=15)

        # Detect distro for Docker repo
        distro = conn.run("bash -c '. /etc/os-release && echo $ID'", timeout=15)
        distro_name = distro.stdout.strip().lower() if distro.returncode == 0 else "ubuntu"

        codename = conn.run("bash -c '. /etc/os-release && echo $VERSION_CODENAME'", timeout=15)
        distro_codename = codename.stdout.strip() if codename.returncode == 0 else "jammy"

        arch = conn.run("dpkg --print-architecture", timeout=15)
        distro_arch = arch.stdout.strip() if arch.returncode == 0 else "amd64"

        # Add Docker GPG key
        gpg_url = f"https://download.docker.com/linux/{distro_name}/gpg"
        result = conn.run(
            f"curl -fsSL {shlex.quote(gpg_url)} -o /etc/apt/keyrings/docker.asc"
            " && chmod 644 /etc/apt/keyrings/docker.asc",
            timeout=60,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to add Docker GPG key: {result.stderr.strip()[:200]}",
            )

        # Add Docker apt repository
        repo_line = (
            f"deb [arch={distro_arch} signed-by=/etc/apt/keyrings/docker.asc] "
            f"https://download.docker.com/linux/{distro_name} "
            f"{distro_codename} stable"
        )
        result = conn.run(
            f"echo {shlex.quote(repo_line)} > /etc/apt/sources.list.d/docker.list",
            timeout=15,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to add Docker repo: {result.stderr.strip()[:200]}",
            )

        # Install Docker CE
        result = conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq"
            " && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq"
            " docker-ce docker-ce-cli containerd.io docker-compose-plugin",
            timeout=300,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
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
                detail=f"docker-ce install failed: {stderr[:200]}",
            )

        # Ensure Docker service is started and enabled
        conn.run("systemctl start docker", timeout=15)
        conn.run("systemctl enable docker", timeout=15)

        # Disable secretservice credential helper — headless servers lack D-Bus
        # secret service, which makes `docker compose pull` fail even for
        # public images.  Stripping credsStore lets Docker work without a
        # keyring while preserving the rest of the config.
        conn.run(
            "test -f ~/.docker/config.json"
            " && jq 'del(.credsStore)' ~/.docker/config.json > ~/.docker/config.json.tmp"
            " && mv ~/.docker/config.json.tmp ~/.docker/config.json"
            " || true",
            timeout=15,
        )

        return StepResult(name=self.name, status="changed")


class Deploy3xui:
    """Deploy 3x-ui panel as a Docker container."""

    name = "Deploy 3x-ui panel"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Create data directories
        for d in ("/opt/3x-ui", "/opt/3x-ui/db", "/opt/3x-ui/cert"):
            result = conn.run(f"mkdir -p {d} && chmod 700 {d}", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to create {d}: {result.stderr.strip()[:200]}",
                )

        # Check port 443 for conflicting services
        port_check = conn.run("ss -tlnp sport = :443", timeout=15)
        if port_check.returncode == 0 and ":443" in port_check.stdout:
            # Check if the service is one of our allowed ones
            stdout = port_check.stdout
            if not any(svc in stdout for svc in _PORT_443_ALLOWED):
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=(
                        f"Port 443 is in use by another service. "
                        f"Stop it first: systemctl stop nginx apache2\n"
                        f"{stdout.strip()[:300]}"
                    ),
                )

        # Write docker-compose.yml
        compose_content = _render_compose(ctx)
        # Use heredoc to write file — avoids shell quoting issues with YAML
        write_cmd = "cat > /opt/3x-ui/docker-compose.yml << 'MERIDIAN_EOF'\n" + compose_content + "MERIDIAN_EOF"
        result = conn.run(write_cmd, timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write docker-compose.yml: {result.stderr.strip()[:200]}",
            )
        conn.run("chmod 644 /opt/3x-ui/docker-compose.yml", timeout=15)

        # Pull the 3x-ui image (with retries)
        pull_ok = False
        for attempt in range(3):
            result = conn.run("cd /opt/3x-ui && docker compose pull", timeout=300)
            if result.returncode == 0:
                pull_ok = True
                break
            if attempt < 2:
                time.sleep(10)

        if not pull_ok:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"docker compose pull failed after 3 attempts: {result.stderr.strip()[:200]}",
            )

        # Start the container
        result = conn.run("cd /opt/3x-ui && docker compose up -d", timeout=120)
        if result.returncode != 0:
            # Rescue: capture logs for diagnosis
            logs = conn.run("cd /opt/3x-ui && docker compose logs --tail 50", timeout=15)
            log_output = logs.stdout.strip()[:500] if logs.returncode == 0 else "no logs available"
            return StepResult(
                name=self.name,
                status="failed",
                detail=(
                    f"docker compose up failed: {result.stderr.strip()[:200]}\n"
                    f"Container logs:\n{log_output}\n"
                    f"Common fixes: check port 443 (ss -tlnp | grep 443), "
                    f"disk space (df -h), Docker status (systemctl status docker)"
                ),
            )

        # Wait for the panel to become responsive
        try:
            _wait_for_panel(conn, ctx.panel_port, web_base_path="")
        except PanelError:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"3x-ui panel did not respond at port {ctx.panel_port} after 60s",
            )

        return StepResult(name=self.name, status="changed")
