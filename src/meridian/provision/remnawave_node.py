"""Remnawave node provisioning step.

Deploys the Remnawave node container on a proxy server. The node uses
host networking so Xray can bind to specific localhost ports. The node
API port is used for panel→node communication (mTLS, token-authenticated).
"""

from __future__ import annotations

import shlex
import time

from meridian.config import (
    REMNAWAVE_NODE_API_PORT,
    REMNAWAVE_NODE_DIR,
    REMNAWAVE_NODE_IMAGE,
)
from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# Container name used for the node
_NODE_CONTAINER = "remnawave-node"


def _render_node_compose(image: str, node_api_port: int) -> str:
    """Render the docker-compose.yml for the Remnawave node."""
    return f"""\
# Remnawave Node - Xray Proxy Node
# Managed by Meridian. Manual edits will be overwritten on next run.
services:
  remnawave-node:
    image: {image}
    container_name: {_NODE_CONTAINER}
    restart: unless-stopped
    # Host networking required so Xray can bind to specific ports
    network_mode: host
    env_file:
      - .env
    volumes:
      - ./logs:/var/log/remnawave
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
"""


def _render_node_env(node_api_port: int, secret_key: str) -> str:
    """Render the .env file for the Remnawave node."""
    return f"""\
# Remnawave Node environment
# Managed by Meridian. Manual edits will be overwritten on next run.

NODE_PORT={node_api_port}
SECRET_KEY={secret_key}
"""


def _wait_for_remnawave_node(
    conn: ServerConnection,
    node_api_port: int,
    retries: int = 20,
    delay: float = 3.0,
) -> None:
    """Poll the node port until responsive or retries exhausted."""
    for _ in range(retries):
        result = conn.run(
            f"ss -tlnp 'sport = :{node_api_port}' | grep -q ':{node_api_port}'",
            timeout=15,
        )
        if result.returncode == 0:
            return
        time.sleep(delay)

    raise RuntimeError(
        f"Remnawave node did not become responsive on port {node_api_port} "
        f"after {retries * delay:.0f}s. "
        f"Check: docker logs {_NODE_CONTAINER} --tail 30"
    )


class DeployRemnawaveNode:
    """Deploy Remnawave node container on a proxy server.

    The node uses ``network_mode: host`` so Xray can bind to specific
    localhost ports. The SECRET_KEY (base64 JSON with mTLS certs) must
    be provided via the provision context (``ctx.get("node_secret_key")``)
    by a prior step that calls the panel API to register the node.

    Idempotency: skipped when the container is already running.
    """

    name = "Deploy Remnawave node"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        node_dir = REMNAWAVE_NODE_DIR
        node_api_port = REMNAWAVE_NODE_API_PORT
        image = REMNAWAVE_NODE_IMAGE

        # -- Retrieve SECRET_KEY from provision context --
        secret_key: str | None = ctx.get("node_secret_key")
        if not secret_key:
            return StepResult(
                name=self.name,
                status="failed",
                detail=(
                    "node_secret_key not found in provision context — "
                    "a prior step must call the panel API to register the node "
                    "and store the mTLS certificate bundle as ctx['node_secret_key']"
                ),
            )

        # -- Idempotency check: is the container already running? --
        running_check = conn.run(
            f"docker inspect -f '{{{{.State.Running}}}}' {_NODE_CONTAINER} 2>/dev/null",
            timeout=15,
        )
        if running_check.returncode == 0 and running_check.stdout.strip() == "true":
            return StepResult(
                name=self.name,
                status="skipped",
                detail="container already running",
            )

        # -- Create directory structure --
        for d in (node_dir, f"{node_dir}/logs"):
            result = conn.run(f"mkdir -p {d} && chmod 700 {d}", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to create {d}: {result.stderr.strip()[:200]}",
                )

        # -- Write .env file --
        env_content = _render_node_env(node_api_port=node_api_port, secret_key=secret_key)
        env_path = f"{node_dir}/.env"
        write_env = f"cat > {shlex.quote(env_path)} << 'MERIDIAN_EOF'\n{env_content}MERIDIAN_EOF"
        result = conn.run(write_env, timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write .env: {result.stderr.strip()[:200]}",
            )
        conn.run(f"chmod 600 {shlex.quote(env_path)}", timeout=15)

        # -- Write docker-compose.yml --
        compose_content = _render_node_compose(image=image, node_api_port=node_api_port)
        compose_path = f"{node_dir}/docker-compose.yml"
        write_compose = f"cat > {shlex.quote(compose_path)} << 'MERIDIAN_EOF'\n{compose_content}MERIDIAN_EOF"
        result = conn.run(write_compose, timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write docker-compose.yml: {result.stderr.strip()[:200]}",
            )
        conn.run(f"chmod 644 {shlex.quote(compose_path)}", timeout=15)

        # -- Pull image (with retries) --
        q_dir = shlex.quote(node_dir)
        pull_ok = False
        pull_result = None
        for attempt in range(3):
            pull_result = conn.run(f"cd {q_dir} && docker compose pull", timeout=300)
            if pull_result.returncode == 0:
                pull_ok = True
                break
            if attempt < 2:
                time.sleep(10)

        if not pull_ok:
            stderr = pull_result.stderr.strip()[:200] if pull_result else "unknown"
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"docker compose pull failed after 3 attempts: {stderr}",
            )

        # -- Start container --
        result = conn.run(f"cd {q_dir} && docker compose up -d", timeout=120)
        if result.returncode != 0:
            logs = conn.run(f"cd {q_dir} && docker compose logs --tail 50", timeout=15)
            log_output = logs.stdout.strip()[:500] if logs.returncode == 0 else "no logs available"
            return StepResult(
                name=self.name,
                status="failed",
                detail=(
                    f"docker compose up failed: {result.stderr.strip()[:200]}\n"
                    f"Container logs:\n{log_output}\n"
                    f"Common fixes: check disk space (df -h), "
                    f"Docker status (systemctl status docker)"
                ),
            )

        # -- Wait for node to become responsive --
        try:
            _wait_for_remnawave_node(conn, node_api_port)
        except RuntimeError as e:
            return StepResult(
                name=self.name,
                status="failed",
                detail=str(e),
            )

        return StepResult(name=self.name, status="changed")
