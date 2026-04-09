"""Core provisioning abstractions: Step, StepResult, ProvisionContext, Provisioner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from typing import Protocol as TypingProtocol

from rich.console import Console
from rich.status import Status

from meridian.config import DEFAULT_PANEL_PORT, DEFAULT_SNI
from meridian.ssh import ServerConnection

if TYPE_CHECKING:
    from meridian.credentials import ServerCredentials
    from meridian.panel import PanelClient

StepStatus = Literal["ok", "changed", "skipped", "failed"]


@dataclass
class StepResult:
    """Result of a provisioning step."""

    name: str  # Human-readable name: "Install Docker"
    status: StepStatus
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
    pq_encryption: bool = False  # post-quantum VLESS encryption (experimental)
    warp: bool = False  # route egress through Cloudflare WARP (SOCKS5 proxy mode)
    geo_block: bool = True  # block Russian domains/IPs at Xray routing level
    hosted_page: bool = False  # serve connection pages via HTTPS on server
    harden: bool = True  # enable SSH hardening + firewall (skip for shared servers)
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
        """Whether this setup needs nginx (domain mode OR hosted page)."""
        return self.domain_mode or self.hosted_page

    def __getitem__(self, key: str) -> Any:
        return self._state[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._state[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._state

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    # --- Typed accessors for key inter-step state ---
    # These document the implicit schema and catch typos at development time.

    @property
    def panel(self) -> PanelClient | None:
        """Logged-in PanelClient, set by LoginToPanel."""
        return self._state.get("panel")

    @panel.setter
    def panel(self, value: PanelClient) -> None:
        self._state["panel"] = value

    @property
    def credentials(self) -> ServerCredentials | None:
        """ServerCredentials, set by ConfigurePanel."""
        return self._state.get("credentials")

    @credentials.setter
    def credentials(self, value: ServerCredentials) -> None:
        self._state["credentials"] = value


class StepContext(TypingProtocol):
    """Minimal protocol for step contexts (ProvisionContext, RelayContext, etc.)."""

    results: list[StepResult]


class Step(TypingProtocol):
    """Protocol for provisioning steps.

    ``ctx`` is typed as ``Any`` because concrete steps use either
    ``ProvisionContext`` (deploy pipeline) or ``RelayContext`` (relay pipeline).
    Both satisfy ``StepContext`` but carry distinct extra fields.
    ``Provisioner.run()`` is similarly ``Any``-typed.
    """

    name: str

    def run(self, conn: ServerConnection, ctx: Any) -> StepResult: ...


class Provisioner:
    """Runs a list of steps with Rich progress output."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps

    def run(self, conn: ServerConnection, ctx: Any) -> list[StepResult]:
        """Execute all steps, collecting results. Shows Rich spinner per step.

        Accepts any context type (ProvisionContext, RelayContext, etc.)
        as long as steps can consume it.  If ``ctx`` has a ``results``
        attribute, each result is appended there too.
        """
        console = Console(stderr=True, highlight=False)
        results: list[StepResult] = []

        total = len(self.steps)
        for i, step in enumerate(self.steps):
            start = time.monotonic()
            prefix = f"[{i + 1}/{total}]"
            with Status(f"  [cyan]{prefix} {step.name}[/cyan]", console=console, spinner="dots"):
                result = step.run(conn, ctx)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result.duration_ms = elapsed_ms

            results.append(result)
            if hasattr(ctx, "results"):
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

        return results
