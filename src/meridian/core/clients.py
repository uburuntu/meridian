"""Client API result models for meridian-core."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from pydantic import Field

from meridian.core.models import CoreModel


class PanelUserLike(Protocol):
    @property
    def uuid(self) -> str: ...

    @property
    def short_uuid(self) -> str: ...

    @property
    def username(self) -> str: ...

    @property
    def vless_uuid(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def used_traffic_bytes(self) -> int: ...

    @property
    def traffic_limit_bytes(self) -> int: ...

    @property
    def created_at(self) -> str: ...

    @property
    def online_at(self) -> str: ...


class ClientRecord(CoreModel):
    """Redacted client metadata suitable for list views."""

    username: str
    uuid: str
    status: str
    traffic_used_bytes: int
    traffic_limit_bytes: int
    created_at: str
    last_seen: str


class ClientDetail(ClientRecord):
    """Client metadata plus optional handoff links."""

    share_url: str = ""
    subscription_url: str = ""


class ClientListSummary(CoreModel):
    """Aggregate client counts for dashboards."""

    clients: int
    active: int
    disabled: int
    limited: int
    expired: int
    other: int

    @property
    def text(self) -> str:
        suffix = "s" if self.clients != 1 else ""
        return f"{self.clients} client{suffix}"


class ClientListResult(CoreModel):
    """Result for listing clients."""

    summary: ClientListSummary
    clients: list[ClientRecord] = Field(default_factory=list)

    def to_data(self) -> dict[str, Any]:
        from meridian.core.serde import to_plain

        return to_plain(self)


class ClientShowResult(CoreModel):
    """Result for showing one client."""

    client: ClientDetail

    def to_data(self) -> dict[str, Any]:
        from meridian.core.serde import to_plain

        return to_plain(self)


def build_client_record(user: PanelUserLike) -> ClientRecord:
    """Build a redacted client record from a panel user object."""
    return ClientRecord(
        username=user.username,
        uuid=user.uuid,
        status=user.status,
        traffic_used_bytes=user.used_traffic_bytes,
        traffic_limit_bytes=user.traffic_limit_bytes,
        created_at=user.created_at,
        last_seen=user.online_at,
    )


def build_client_detail(user: PanelUserLike, *, share_url: str = "", subscription_url: str = "") -> ClientDetail:
    """Build one client detail result from panel state and handoff links."""
    base = build_client_record(user)
    return ClientDetail(
        **base.model_dump(),
        share_url=share_url,
        subscription_url=subscription_url,
    )


def build_client_list_result(users: Sequence[PanelUserLike]) -> ClientListResult:
    """Build a client list result with status counts."""
    records = [build_client_record(user) for user in users]
    statuses = [record.status.upper() for record in records]
    active = sum(1 for status in statuses if status == "ACTIVE")
    disabled = sum(1 for status in statuses if status == "DISABLED")
    limited = sum(1 for status in statuses if status == "LIMITED")
    expired = sum(1 for status in statuses if status == "EXPIRED")
    other = len(statuses) - active - disabled - limited - expired
    return ClientListResult(
        summary=ClientListSummary(
            clients=len(records),
            active=active,
            disabled=disabled,
            limited=limited,
            expired=expired,
            other=other,
        ),
        clients=records,
    )


def build_client_show_result(
    user: PanelUserLike,
    *,
    share_url: str = "",
    subscription_url: str = "",
) -> ClientShowResult:
    """Build a one-client result with optional handoff links."""
    return ClientShowResult(
        client=build_client_detail(user, share_url=share_url, subscription_url=subscription_url),
    )
