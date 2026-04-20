"""Clean up legacy 3x-ui panel from v3 deployments.

Idempotent: returns 'skipped' when no 3x-ui container or directory exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from meridian.provision.steps import StepResult

if TYPE_CHECKING:
    from meridian.ssh import ServerConnection


class CleanupLegacyPanel:
    """Remove the 3x-ui panel container and data directory.

    v3 deployed 3x-ui at /opt/3x-ui.  When upgrading to v4 (Remnawave),
    the old container must be stopped to free ports and avoid conflicts.
    """

    name = "Remove legacy 3x-ui panel"

    def run(self, conn: ServerConnection, ctx: Any) -> StepResult:
        # Check if 3x-ui container exists (running or stopped)
        container = conn.run("docker inspect 3x-ui 2>/dev/null", timeout=15)
        has_container = container.returncode == 0

        directory = conn.run("test -d /opt/3x-ui", timeout=10)
        has_directory = directory.returncode == 0

        if not has_container and not has_directory:
            return StepResult(
                name=self.name,
                status="skipped",
                detail="no legacy panel found",
            )

        # Stop and remove 3x-ui container + images
        if has_container:
            conn.run(
                "cd /opt/3x-ui && docker compose down --rmi all 2>/dev/null; true",
                timeout=60,
            )
            # Also handle standalone container (some v3 versions)
            conn.run("docker stop 3x-ui 2>/dev/null; docker rm 3x-ui 2>/dev/null; true", timeout=30)

        # Remove data directory
        if has_directory:
            conn.run("rm -rf /opt/3x-ui", timeout=15)

        return StepResult(
            name=self.name,
            status="changed",
            detail="removed 3x-ui container and data",
        )
