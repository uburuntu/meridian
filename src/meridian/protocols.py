"""Protocol/inbound type definitions — single source of truth.

Keep in sync with inbound_types in group_vars/all.yml.

Adding a new protocol (e.g., Hysteria2, TUIC) requires:
1. Add an InboundType entry to INBOUND_TYPES
2. Create a Protocol subclass below
3. Append an instance to the PROTOCOLS list

The rest of the system (client add/remove, output generation) will
pick up the new protocol automatically via the registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from meridian.panel import Inbound


@dataclass(frozen=True)
class InboundType:
    """Defines an inbound protocol type in 3x-ui."""

    remark: str  # 3x-ui inbound remark (e.g., "VLESS-Reality")
    email_prefix: str  # Client email prefix (e.g., "reality-")
    flow: str  # Xray flow value (e.g., "xtls-rprx-vision")
    url_scheme: str = "vless"  # URL scheme for connection strings


# Single source of truth for all inbound types.
# Ansible equivalent: inbound_types in group_vars/all.yml
INBOUND_TYPES: dict[str, InboundType] = {
    "reality": InboundType(
        remark="VLESS-Reality",
        email_prefix="reality-",
        flow="xtls-rprx-vision",
    ),
    "wss": InboundType(
        remark="VLESS-WSS",
        email_prefix="wss-",
        flow="",
    ),
    "xhttp": InboundType(
        remark="VLESS-Reality-XHTTP",
        email_prefix="xhttp-",
        flow="",
    ),
}


# ---------------------------------------------------------------------------
# Protocol abstraction
# ---------------------------------------------------------------------------


class Protocol(ABC):
    """Base class for proxy protocols.

    Each Protocol knows how to:
    - Build a connection URL for a given client UUID
    - Build the 3x-ui addClient API body
    - Determine if it's available on a server (by inspecting inbounds)
    """

    @property
    @abstractmethod
    def key(self) -> str:
        """Protocol key (e.g., 'reality', 'wss', 'xhttp')."""
        ...

    @property
    @abstractmethod
    def inbound_type(self) -> InboundType:
        """The inbound type definition."""
        ...

    @property
    def remark(self) -> str:
        """Convenience: the 3x-ui inbound remark for this protocol."""
        return self.inbound_type.remark

    @property
    def email_prefix(self) -> str:
        """Convenience: email prefix for client emails."""
        return self.inbound_type.email_prefix

    @abstractmethod
    def build_url(self, uuid: str, name: str, **kwargs: Any) -> str:
        """Build a connection URL for this protocol.

        Args:
            uuid: Client UUID.
            name: Client display name (used in URL fragment).
            **kwargs: Protocol-specific parameters (ip, port, sni, etc.).

        Returns:
            A complete VLESS/etc URL string.
        """
        ...

    @abstractmethod
    def client_settings(self, uuid: str, email: str) -> dict[str, Any]:
        """Build the client settings dict for the 3x-ui addClient API.

        Returns a dict with 'clients' key containing a single-element list:
            {"clients": [{"id": uuid, "flow": ..., "email": ..., ...}]}
        """
        ...

    def find_inbound(self, inbounds: list[Inbound]) -> Inbound | None:
        """Find this protocol's inbound in a list of panel inbounds."""
        for ib in inbounds:
            if ib.remark == self.remark:
                return ib
        return None

    @property
    def requires_domain(self) -> bool:
        """Whether this protocol requires a domain to function."""
        return False

    @property
    def shares_uuid_with(self) -> str | None:
        """Key of another protocol this one shares a UUID with.

        For example, XHTTP shares the Reality UUID.
        None means this protocol uses its own UUID.
        """
        return None

    @property
    def url_suffix(self) -> str:
        """Suffix appended to client name in the URL fragment (e.g., '-XHTTP')."""
        return ""


class RealityProtocol(Protocol):
    """VLESS + Reality + TCP — primary protocol, always present."""

    @property
    def key(self) -> str:
        return "reality"

    @property
    def inbound_type(self) -> InboundType:
        return INBOUND_TYPES["reality"]

    def build_url(self, uuid: str, name: str, **kwargs: Any) -> str:
        ip = kwargs["ip"]
        sni = kwargs.get("sni", "www.microsoft.com")
        public_key = kwargs.get("public_key", "")
        short_id = kwargs.get("short_id", "")
        fingerprint = kwargs.get("fingerprint", "chrome")
        return (
            f"vless://{uuid}@{ip}:443"
            f"?encryption=none&flow=xtls-rprx-vision"
            f"&security=reality&sni={sni}&fp={fingerprint}"
            f"&pbk={public_key}&sid={short_id}"
            f"&type=tcp&headerType=none"
            f"#{name}"
        )

    def client_settings(self, uuid: str, email: str) -> dict[str, Any]:
        return {
            "clients": [
                {
                    "id": uuid,
                    "flow": self.inbound_type.flow,
                    "email": email,
                    "limitIp": 2,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0,
                }
            ]
        }


class XHTTPProtocol(Protocol):
    """VLESS + Reality + XHTTP — enhanced stealth transport."""

    @property
    def key(self) -> str:
        return "xhttp"

    @property
    def inbound_type(self) -> InboundType:
        return INBOUND_TYPES["xhttp"]

    @property
    def shares_uuid_with(self) -> str | None:
        return "reality"

    @property
    def url_suffix(self) -> str:
        return "-XHTTP"

    def build_url(self, uuid: str, name: str, **kwargs: Any) -> str:
        ip = kwargs["ip"]
        port = kwargs["port"]
        sni = kwargs.get("sni", "www.microsoft.com")
        public_key = kwargs.get("public_key", "")
        short_id = kwargs.get("short_id", "")
        fingerprint = kwargs.get("fingerprint", "chrome")
        return (
            f"vless://{uuid}@{ip}:{port}"
            f"?encryption=none"
            f"&security=reality&sni={sni}&fp={fingerprint}"
            f"&pbk={public_key}&sid={short_id}"
            f"&type=xhttp&mode=packet-up&path=%2F"
            f"#{name}-XHTTP"
        )

    def client_settings(self, uuid: str, email: str) -> dict[str, Any]:
        return {
            "clients": [
                {
                    "id": uuid,
                    "flow": self.inbound_type.flow,
                    "email": email,
                    "limitIp": 2,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0,
                }
            ]
        }


class WSSProtocol(Protocol):
    """VLESS + WSS — CDN fallback via Caddy/Cloudflare."""

    @property
    def key(self) -> str:
        return "wss"

    @property
    def inbound_type(self) -> InboundType:
        return INBOUND_TYPES["wss"]

    @property
    def requires_domain(self) -> bool:
        return True

    @property
    def url_suffix(self) -> str:
        return "-WSS"

    def build_url(self, uuid: str, name: str, **kwargs: Any) -> str:
        domain = kwargs["domain"]
        ws_path = kwargs.get("ws_path", "")
        return (
            f"vless://{uuid}@{domain}:443"
            f"?encryption=none&security=tls&sni={domain}"
            f"&type=ws&host={domain}&path=%2F{ws_path}"
            f"#{name}-WSS"
        )

    def client_settings(self, uuid: str, email: str) -> dict[str, Any]:
        return {
            "clients": [
                {
                    "id": uuid,
                    "flow": self.inbound_type.flow,
                    "email": email,
                    "limitIp": 2,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0,
                }
            ]
        }


# ---------------------------------------------------------------------------
# Protocol registry
# ---------------------------------------------------------------------------

# Ordered: Reality first (primary), then XHTTP, then WSS.
PROTOCOLS: list[Protocol] = [
    RealityProtocol(),
    XHTTPProtocol(),
    WSSProtocol(),
]


def get_protocol(key: str) -> Protocol | None:
    """Find a protocol by key (e.g., 'reality', 'wss', 'xhttp')."""
    for proto in PROTOCOLS:
        if proto.key == key:
            return proto
    return None


def available_protocols(
    inbounds: list[Inbound],
    domain: str = "",
) -> list[Protocol]:
    """Return protocols that are available on this server.

    A protocol is available when:
    1. Its inbound exists in the panel (matched by remark)
    2. If it requires a domain, a domain is configured
    """
    result: list[Protocol] = []
    for proto in PROTOCOLS:
        if proto.find_inbound(inbounds) is None:
            continue
        if proto.requires_domain and not domain:
            continue
        result.append(proto)
    return result
