"""Remnawave panel provisioning step.

Deploys the Remnawave backend (panel) and PostgreSQL database as Docker
containers on the server. The panel listens on 127.0.0.1:3000 and is
never exposed directly — nginx reverse-proxies to it.
"""

from __future__ import annotations

import secrets
import shlex
import time

from meridian.config import (
    REMNAWAVE_BACKEND_IMAGE,
    REMNAWAVE_PANEL_DIR,
    REMNAWAVE_PANEL_PORT,
)
from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# Container name used for the panel backend
_PANEL_CONTAINER = "remnawave"
_DB_CONTAINER = "remnawave-db"


def _render_panel_compose(
    image: str,
    panel_port: int,
    db_password: str,
    jwt_auth_secret: str,
    jwt_api_secret: str,
    front_end_domain: str,
    sub_public_domain: str,
) -> str:
    """Render the docker-compose.yml for the Remnawave panel stack."""
    return f"""\
# Remnawave Panel - VPN Management Interface
# Managed by Meridian. Manual edits will be overwritten on next run.
services:
  remnawave:
    image: {image}
    container_name: {_PANEL_CONTAINER}
    restart: unless-stopped
    depends_on:
      remnawave-db:
        condition: service_healthy
    networks:
      - remnawave-net
    ports:
      - "127.0.0.1:{panel_port}:{panel_port}"
    env_file:
      - .env
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  remnawave-db:
    image: postgres:16-alpine
    container_name: {_DB_CONTAINER}
    restart: unless-stopped
    networks:
      - remnawave-net
    volumes:
      - ./data:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: meridian
      POSTGRES_PASSWORD: "{db_password}"
      POSTGRES_DB: remnawave
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U meridian -d remnawave"]
      interval: 5s
      timeout: 5s
      retries: 10
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

networks:
  remnawave-net:
    driver: bridge
"""


def _render_panel_env(
    panel_port: int,
    db_password: str,
    jwt_auth_secret: str,
    jwt_api_secret: str,
    front_end_domain: str,
    sub_public_domain: str,
) -> str:
    """Render the .env file for the Remnawave panel."""
    return f"""\
# Remnawave Panel environment
# Managed by Meridian. Manual edits will be overwritten on next run.

APP_PORT={panel_port}
DATABASE_URL=postgresql://meridian:{db_password}@remnawave-db:5432/remnawave

JWT_AUTH_SECRET={jwt_auth_secret}
JWT_API_TOKENS_SECRET={jwt_api_secret}

FRONT_END_DOMAIN={front_end_domain}
SUB_PUBLIC_DOMAIN={sub_public_domain}

WEBHOOK_ENABLED=false
NODES_NOTIFY_ENABLED=false
IS_PANEL_NODE=false
"""


def _wait_for_remnawave_panel(
    conn: ServerConnection,
    panel_port: int,
    retries: int = 30,
    delay: float = 3.0,
) -> None:
    """Poll the Remnawave health endpoint until responsive or retries exhausted."""
    url = f"http://127.0.0.1:{panel_port}/api/health"
    q_url = shlex.quote(url)

    for _ in range(retries):
        result = conn.run(
            f"curl -s -o /dev/null -w '%{{http_code}}' {q_url}",
            timeout=15,
        )
        code = result.stdout.strip()
        if result.returncode == 0 and code and code != "000":
            return
        time.sleep(delay)

    raise RuntimeError(
        f"Remnawave panel did not become responsive at port {panel_port} "
        f"after {retries * delay:.0f}s. "
        f"Check: docker logs {_PANEL_CONTAINER} --tail 30"
    )


class DeployRemnawavePanel:
    """Deploy Remnawave panel (backend + PostgreSQL) as Docker containers.

    Idempotency: skipped when both containers are already running.

    Secrets generated here are stored in the provision context under:
      - ctx["remnawave_db_password"]
      - ctx["remnawave_jwt_auth_secret"]
      - ctx["remnawave_jwt_api_secret"]
    for use by downstream steps (e.g. panel API bootstrap, node registration).
    """

    name = "Deploy Remnawave panel"

    def __init__(
        self,
        front_end_domain: str = "",
        sub_public_domain: str = "",
    ) -> None:
        self.front_end_domain = front_end_domain
        self.sub_public_domain = sub_public_domain

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        panel_dir = REMNAWAVE_PANEL_DIR
        panel_port = REMNAWAVE_PANEL_PORT
        image = REMNAWAVE_BACKEND_IMAGE

        # Resolve domains from context when not provided to constructor
        front_end_domain = self.front_end_domain or ctx.domain or ctx.ip
        sub_public_domain = self.sub_public_domain or ctx.domain or ctx.ip

        # -- Idempotency check: are both containers already running? --
        panel_check = conn.run(
            f"docker inspect -f '{{{{.State.Running}}}}' {_PANEL_CONTAINER} 2>/dev/null",
            timeout=15,
        )
        db_check = conn.run(
            f"docker inspect -f '{{{{.State.Running}}}}' {_DB_CONTAINER} 2>/dev/null",
            timeout=15,
        )
        both_running = (
            panel_check.returncode == 0
            and panel_check.stdout.strip() == "true"
            and db_check.returncode == 0
            and db_check.stdout.strip() == "true"
        )
        if both_running:
            # Re-read secrets from the existing .env so downstream steps
            # can still use them even on a skipped run.
            env_read = conn.run(f"cat {panel_dir}/.env 2>/dev/null", timeout=15)
            if env_read.returncode == 0:
                _load_env_into_ctx(env_read.stdout, ctx)
            return StepResult(
                name=self.name,
                status="skipped",
                detail="containers already running",
            )

        # -- Create directory structure --
        for d in (panel_dir, f"{panel_dir}/data"):
            result = conn.run(f"mkdir -p {d} && chmod 700 {d}", timeout=15)
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"failed to create {d}: {result.stderr.strip()[:200]}",
                )

        # -- Generate secrets --
        db_password = secrets.token_hex(16)          # 32-char hex
        jwt_auth_secret = secrets.token_hex(32)      # 64-char hex
        jwt_api_secret = secrets.token_hex(32)       # 64-char hex

        # -- Write .env file --
        env_content = _render_panel_env(
            panel_port=panel_port,
            db_password=db_password,
            jwt_auth_secret=jwt_auth_secret,
            jwt_api_secret=jwt_api_secret,
            front_end_domain=front_end_domain,
            sub_public_domain=sub_public_domain,
        )
        env_path = f"{panel_dir}/.env"
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
        compose_content = _render_panel_compose(
            image=image,
            panel_port=panel_port,
            db_password=db_password,
            jwt_auth_secret=jwt_auth_secret,
            jwt_api_secret=jwt_api_secret,
            front_end_domain=front_end_domain,
            sub_public_domain=sub_public_domain,
        )
        compose_path = f"{panel_dir}/docker-compose.yml"
        write_compose = f"cat > {shlex.quote(compose_path)} << 'MERIDIAN_EOF'\n{compose_content}MERIDIAN_EOF"
        result = conn.run(write_compose, timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"failed to write docker-compose.yml: {result.stderr.strip()[:200]}",
            )
        conn.run(f"chmod 644 {shlex.quote(compose_path)}", timeout=15)

        # -- Pull images (with retries) --
        q_dir = shlex.quote(panel_dir)
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

        # -- Start containers --
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

        # -- Wait for panel to become healthy --
        try:
            _wait_for_remnawave_panel(conn, panel_port)
        except RuntimeError as e:
            return StepResult(
                name=self.name,
                status="failed",
                detail=str(e),
            )

        # -- Store secrets in context for downstream steps --
        ctx["remnawave_db_password"] = db_password
        ctx["remnawave_jwt_auth_secret"] = jwt_auth_secret
        ctx["remnawave_jwt_api_secret"] = jwt_api_secret

        return StepResult(name=self.name, status="changed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_env_into_ctx(env_text: str, ctx: ProvisionContext) -> None:
    """Parse key=value lines from .env content and populate known ctx keys."""
    key_map = {
        "REMNAWAVE_DB_PASSWORD": "remnawave_db_password",
        "JWT_AUTH_SECRET": "remnawave_jwt_auth_secret",
        "JWT_API_TOKENS_SECRET": "remnawave_jwt_api_secret",
    }
    # Also handle DATABASE_URL to extract password if dedicated key absent
    for line in env_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        raw_key, _, raw_val = line.partition("=")
        env_key = raw_key.strip()
        env_val = raw_val.strip()
        if env_key in key_map:
            ctx[key_map[env_key]] = env_val
