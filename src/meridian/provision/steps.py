"""Core provisioning abstractions: Step, StepResult, ProvisionContext, Provisioner."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from typing import Protocol as TypingProtocol

from rich.console import Console
from rich.status import Status

from meridian.config import DEFAULT_SNI

if TYPE_CHECKING:
    from meridian.cluster import ClusterConfig
    from meridian.remnawave import MeridianPanel
    from meridian.ssh import ServerConnection

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

    Typed fields for well-known configuration AND typed accessors for
    inter-step communication. The _state dict is kept for edge cases
    but typed properties are the preferred interface.
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
    is_panel_host: bool = True  # deploy Remnawave panel on this server

    results: list[StepResult] = field(default_factory=list)

    # Port layout — Xray ports configured in Remnawave config profile
    xhttp_port: int = 0  # computed from seed
    reality_port: int = 443  # 443 standalone, ~10443 domain mode
    wss_port: int = 0  # computed from seed (domain mode only)

    @property
    def panel_port(self) -> int:
        """Panel internal port (Remnawave: 3000, legacy 3x-ui: 2053)."""
        from meridian.config import REMNAWAVE_PANEL_PORT

        return REMNAWAVE_PANEL_PORT

    # Dynamic inter-step state
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

    # --- Typed accessors for inter-step state ---

    @property
    def panel_api(self) -> MeridianPanel | None:
        """Authenticated MeridianPanel client, set after panel setup."""
        return self._state.get("panel_api")

    @panel_api.setter
    def panel_api(self, value: MeridianPanel) -> None:
        self._state["panel_api"] = value

    @property
    def cluster(self) -> ClusterConfig | None:
        """ClusterConfig being built during deployment."""
        return self._state.get("cluster")

    @cluster.setter
    def cluster(self, value: ClusterConfig) -> None:
        self._state["cluster"] = value

    # Legacy typed accessors (kept for backward compat during migration)
    @property
    def panel(self) -> Any:
        """Legacy: PanelClient for 3x-ui. Use panel_api for Remnawave."""
        return self._state.get("panel")

    @panel.setter
    def panel(self, value: Any) -> None:
        self._state["panel"] = value

    @property
    def credentials(self) -> Any:
        """Legacy: ServerCredentials. Use cluster for 4.0."""
        return self._state.get("credentials")

    @credentials.setter
    def credentials(self, value: Any) -> None:
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

    @property
    def name(self) -> str: ...

    def run(self, conn: ServerConnection, ctx: Any) -> StepResult: ...


class Provisioner:
    """Runs a list of steps with Rich progress output."""

    def __init__(self, steps: Sequence[Step]) -> None:
        self.steps = list(steps)

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
