"""Core provisioning abstractions: Step, StepResult, ProvisionContext, Provisioner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from typing import Protocol as TypingProtocol

from rich.console import Console
from rich.status import Status

from meridian.config import DEFAULT_PANEL_PORT, DEFAULT_SNI
from meridian.ssh import ServerConnection


def timed(fn):  # noqa: ANN001, ANN202
    """Decorator that adds duration_ms to the returned StepResult."""

    def wrapper(*args: Any, **kwargs: Any) -> StepResult:
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result

    return wrapper


@dataclass
class StepResult:
    """Result of a provisioning step."""

    name: str  # Human-readable name: "Install Docker"
    status: str  # "ok" | "changed" | "skipped" | "failed"
    detail: str = ""  # Human-readable detail for tracing
    duration_ms: int = 0


@dataclass
class ProvisionContext:
    """Carries state through the provisioning pipeline.

    Typed fields for well-known configuration. Dynamic dict-like access
    for inter-step communication (e.g., ctx["panel"] for a logged-in PanelClient,
    ctx["credentials"] for ServerCredentials populated by ConfigurePanel).
    """

    ip: str
    user: str = "root"
    domain: str = ""
    sni: str = DEFAULT_SNI
    xhttp_enabled: bool = True
    hosted_page: bool = False  # serve connection pages via HTTPS on server
    creds_dir: str = ""  # local credentials directory path

    results: list[StepResult] = field(default_factory=list)

    # Mutable state populated by steps:
    panel_port: int = DEFAULT_PANEL_PORT  # internal panel port
    xhttp_port: int = 0  # computed from seed
    reality_port: int = 443  # 443 standalone, ~10443 domain mode
    wss_port: int = 0  # computed from seed (domain mode only)

    # 3x-ui image version (pinned to tested release, digest for supply chain integrity)
    threexui_version: str = "2.8.11@sha256:34c46ea6d838df981c4760bd1fe442413c2b99bbe4bb49dfa3d1bfb8a8a92496"

    # Dynamic inter-step state (PanelClient, credentials, UUIDs, etc.)
    _state: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def domain_mode(self) -> bool:
        return bool(self.domain)

    @property
    def needs_web_server(self) -> bool:
        """Whether this setup needs HAProxy + Caddy (domain mode OR hosted page)."""
        return self.domain_mode or self.hosted_page

    def __getitem__(self, key: str) -> Any:
        return self._state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._state[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._state

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)


class Step(TypingProtocol):
    """Protocol for provisioning steps."""

    name: str

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult: ...


class Provisioner:
    """Runs a list of steps with Rich progress output."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> list[StepResult]:
        """Execute all steps, collecting results. Shows Rich spinner per step."""
        console = Console(stderr=True, highlight=False)

        total = len(self.steps)
        for i, step in enumerate(self.steps):
            start = time.monotonic()
            prefix = f"[{i + 1}/{total}]"
            with Status(f"  [cyan]{prefix} {step.name}[/cyan]", console=console, spinner="dots"):
                result = step.run(conn, ctx)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result.duration_ms = elapsed_ms

            ctx.results.append(result)

            if result.status == "failed":
                detail = f" ({result.detail})" if result.detail else ""
                console.print(f"  [red bold]\u2717[/red bold] {result.name}{detail}")
                break
            elif result.status == "skipped":
                detail = f" ({result.detail})" if result.detail else ""
                console.print(f"  [dim]\u2013 {result.name}{detail}[/dim]")
            else:
                # ok or changed
                marker = "\u2713"
                detail = f" [dim]({result.detail})[/dim]" if result.detail else ""
                console.print(f"  [green]{marker}[/green] {result.name}{detail}")

        return ctx.results
