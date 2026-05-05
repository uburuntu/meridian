"""Deploy request/result contracts for meridian-core clients."""

from __future__ import annotations

from typing import Any, Literal

from meridian.core.models import CoreModel
from meridian.core.serde import to_plain

DeployMode = Literal["first_deploy", "redeploy"]


class DeployRequest(CoreModel):
    """Trusted local request for deploying or redeploying a Meridian server."""

    ip: str = ""
    domain: str = ""
    sni: str = ""
    client_name: str = ""
    user: str = "root"
    yes: bool = False
    harden: bool = True
    requested_server: str = ""
    server_name: str = ""
    icon: str = ""
    color: str = ""
    decoy: str = ""
    pq: bool = False
    warp: bool = False
    geo_block: bool = True
    ssh_port: int = 22


class DeployResult(CoreModel):
    """Result returned after a deploy/redeploy operation completes."""

    mode: DeployMode
    server_ip: str
    ssh_user: str
    ssh_port: int
    domain: str
    sni: str
    client_name: str
    harden: bool
    pq: bool
    warp: bool
    geo_block: bool
    panel_url: str
    panel_secret_path: str
    connection_page_path: str
    node_count: int
    relay_count: int
    summary: str

    def to_data(self) -> dict[str, Any]:
        return to_plain(self)
