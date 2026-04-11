"""Docker provisioning step.

InstallDocker is panel-agnostic — it installs Docker CE from the official
repository. The panel/node container deployment is handled by
remnawave_panel.py and remnawave_node.py respectively.
"""

from __future__ import annotations

import shlex

from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# Services allowed on port 443 (our own stack components)
_PORT_443_ALLOWED = ("remnawave", "xray", "nginx", "haproxy", "caddy", "3x-ui")

# Conflicting Docker packages to remove before installing docker-ce
_CONFLICTING_PACKAGES = [
    "docker.io",
    "docker-compose",
    "docker-doc",
    "podman-docker",
    "containerd",
    "runc",
]


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
