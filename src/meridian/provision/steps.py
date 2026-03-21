"""Core provisioning abstractions: Step, StepResult, ProvisionContext, Provisioner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol as TypingProtocol

from rich.console import Console
from rich.status import Status

from meridian.ssh import ServerConnection


@dataclass
class StepResult:
    """Result of a provisioning step."""

    name: str  # Human-readable name: "Install Docker"
    status: str  # "ok" | "changed" | "skipped" | "failed"
    detail: str = ""  # Human-readable detail for tracing
    duration_ms: int = 0


@dataclass
class ProvisionContext:
    """Carries state through the provisioning pipeline."""

    ip: str
    user: str = "root"
    domain: str = ""
    sni: str = "www.microsoft.com"
    xhttp_enabled: bool = True
    creds_dir: str = ""  # local credentials directory path

    results: list[StepResult] = field(default_factory=list)

    # Mutable state populated by steps:
    panel_port: int = 2053  # internal panel port
    xhttp_port: int = 0  # computed from seed
    reality_port: int = 443  # 443 standalone, ~10443 domain mode

    # 3x-ui image version (pinned to tested release)
    threexui_version: str = "2.8.11"

    @property
    def domain_mode(self) -> bool:
        return bool(self.domain)


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

        for step in self.steps:
            start = time.monotonic()
            with Status(f"  [cyan]{step.name}[/cyan]", console=console, spinner="dots"):
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
                marker = "\u2713" if result.status == "ok" else "\u2713"
                detail = f" [dim]({result.detail})[/dim]" if result.detail else ""
                console.print(f"  [green]{marker}[/green] {result.name}{detail}")

        return ctx.results
