"""Structured credential management with YAML persistence.

V2 format uses nested structure: panel, server, protocols, clients.
V1 flat format is auto-migrated on load.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from meridian.config import DEFAULT_PANEL_PORT


@dataclass
class PanelConfig:
    """Panel access credentials and paths."""

    username: str | None = None
    password: str | None = None
    web_base_path: str | None = None
    info_page_path: str | None = None
    port: int = DEFAULT_PANEL_PORT
    url: str = ""
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ServerConfig:
    """Server identity and SNI configuration."""

    ip: str | None = None
    domain: str | None = None
    sni: str | None = None
    scanned_sni: str | None = None
    hosted_page: bool = False
    deployed_with: str = ""  # Meridian CLI version that last deployed this server
    warp: bool = False  # outgoing traffic routed through Cloudflare WARP
    geo_block: bool = True  # block Russian domains/IPs at Xray routing level
    decoy: str = ""  # Decoy response: "" = silent drop, "403" = realistic nginx (403 root + 404 paths)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class RealityConfig:
    """Reality protocol credentials."""

    uuid: str | None = None
    private_key: str | None = None
    public_key: str | None = None
    short_id: str | None = None
    encryption_key: str | None = None  # PQ public key (client URL)
    encryption_private_key: str | None = None  # PQ private key (server decryption)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class WSSConfig:
    """WSS protocol credentials."""

    uuid: str | None = None
    ws_path: str | None = None
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class XHTTPConfig:
    """XHTTP protocol credentials."""

    uuid: str | None = None
    xhttp_path: str | None = None
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ClientEntry:
    """A tracked proxy client."""

    name: str = ""
    added: str = ""
    reality_uuid: str = ""
    wss_uuid: str = ""
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class RelayEntry:
    """A relay node that forwards traffic to this exit server."""

    ip: str = ""
    name: str = ""  # optional friendly name (e.g., "ru-moscow")
    port: int = 443  # relay listen port
    added: str = ""  # ISO8601 timestamp
    sni: str = ""  # relay-specific SNI target for Reality camouflage
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class BrandingConfig:
    """Server branding for connection pages."""

    server_name: str = ""  # display name (e.g., "Alice's VPN")
    icon: str = ""  # emoji or data URI (e.g., "🛡️" or "data:image/png;base64,...")
    color: str = ""  # palette name (ocean, sunset, forest, lavender, rose, slate)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ServerCredentials:
    """Protocol-indexed credential storage (v2 format).

    V2 uses nested structure for panel, server, protocols, and clients.
    V1 flat format is auto-migrated on load; next save() writes v2.
    None means "not set" (distinct from empty string "").
    """

    version: int = 2
    panel: PanelConfig = field(default_factory=PanelConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    protocols: dict[str, Any] = field(default_factory=dict)
    clients: list[ClientEntry] = field(default_factory=list)
    relays: list[RelayEntry] = field(default_factory=list)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    # Extra fields from the YAML that we don't know about (forward-compat)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: Path) -> ServerCredentials:
        """Load from a proxy.yml file. Auto-migrates v1 to v2.

        Returns empty credentials if file doesn't exist.
        """
        if not path.exists():
            return cls()
        raw = path.read_text()
        if not raw.strip():
            return cls()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return cls()

        version = data.get("version", 1)
        if version >= 2:
            return _load_v2(data)
        return _migrate_v1(data)

    def save(self, path: Path) -> None:
        """Write v2 format to proxy.yml (atomic via tempfile+rename)."""
        import os
        import tempfile

        out: dict[str, Any] = {"version": 2}

        # Panel
        panel_dict = _serialize_dataclass(self.panel)
        if panel_dict:
            out["panel"] = panel_dict

        # Server
        server_dict = _serialize_dataclass(self.server)
        if server_dict:
            out["server"] = server_dict

        # Protocols
        if self.protocols:
            protos: dict[str, Any] = {}
            for name, proto in self.protocols.items():
                if hasattr(proto, "__dataclass_fields__"):
                    proto_dict = _serialize_dataclass(proto)
                elif isinstance(proto, dict):
                    proto_dict = _strip_none(proto)
                else:
                    proto_dict = proto
                if proto_dict:
                    protos[name] = proto_dict
            if protos:
                out["protocols"] = protos

        # Clients
        if self.clients:
            out["clients"] = [_serialize_dataclass(c) for c in self.clients]

        # Relays
        if self.relays:
            out["relays"] = [_serialize_dataclass(r) for r in self.relays]

        # Branding
        branding_dict = _serialize_dataclass(self.branding)
        # Known branding fields use empty string as "unset", but preserved
        # forward-compat fields may legitimately be falsy.
        for field_name in ("server_name", "icon", "color"):
            if branding_dict.get(field_name) == "":
                branding_dict.pop(field_name, None)
        if branding_dict:
            out["branding"] = branding_dict

        # Extra fields (forward-compat)
        for k, v in self._extra.items():
            if k not in out:
                out[k] = v

        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Enforce dir permissions even if directory already existed (mkdir ignores mode with exist_ok)
        path.parent.chmod(0o700)
        # Atomic write: tempfile in same directory, then rename
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, yaml.dump(out, default_flow_style=False, sort_keys=False).encode())
            os.close(fd)
            fd = -1  # mark as closed
            os.chmod(tmp, 0o600)
            os.rename(tmp, str(path))
        except BaseException:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # --- Convenience properties ---

    @property
    def has_domain(self) -> bool:
        return bool(self.server.domain)

    @property
    def has_credentials(self) -> bool:
        return bool(self.panel.username and self.panel.password)

    @property
    def reality(self) -> RealityConfig:
        """Get or create the Reality protocol config."""
        if "reality" not in self.protocols:
            self.protocols["reality"] = RealityConfig()
        proto = self.protocols["reality"]
        if isinstance(proto, dict):
            self.protocols["reality"] = _load_known_dataclass(
                proto,
                RealityConfig,
                {"uuid", "private_key", "public_key", "short_id", "encryption_key", "encryption_private_key"},
            )
            return self.protocols["reality"]
        return proto

    @property
    def wss(self) -> WSSConfig:
        """Get or create the WSS protocol config."""
        if "wss" not in self.protocols:
            self.protocols["wss"] = WSSConfig()
        proto = self.protocols["wss"]
        if isinstance(proto, dict):
            self.protocols["wss"] = _load_known_dataclass(proto, WSSConfig, {"uuid", "ws_path"})
            return self.protocols["wss"]
        return proto

    @property
    def xhttp(self) -> XHTTPConfig:
        """Get or create the XHTTP protocol config."""
        if "xhttp" not in self.protocols:
            self.protocols["xhttp"] = XHTTPConfig()
        proto = self.protocols["xhttp"]
        if isinstance(proto, dict):
            self.protocols["xhttp"] = _load_known_dataclass(proto, XHTTPConfig, {"uuid", "xhttp_path"})
            return self.protocols["xhttp"]
        return proto


def creds_path(creds_base: Path, server_ip: str) -> Path:
    """Return the proxy.yml path for a given server IP."""
    from meridian.config import sanitize_ip_for_path

    return creds_base / sanitize_ip_for_path(server_ip) / "proxy.yml"


# --- V1 → V2 migration ---

# Map old flat field names to v2 nested paths
_V1_FIELD_MAP: dict[str, tuple[str, str]] = {
    "panel_username": ("panel", "username"),
    "panel_password": ("panel", "password"),
    "panel_web_base_path": ("panel", "web_base_path"),
    "info_page_path": ("panel", "info_page_path"),
    # server fields
    "exit_ip": ("server", "ip"),
    "server_ip": ("server", "ip"),
    "domain": ("server", "domain"),
    "reality_sni": ("server", "sni"),
    "scanned_sni": ("server", "scanned_sni"),
    # protocol fields
    "reality_uuid": ("protocols.reality", "uuid"),
    "reality_private_key": ("protocols.reality", "private_key"),
    "reality_public_key": ("protocols.reality", "public_key"),
    "reality_short_id": ("protocols.reality", "short_id"),
    "wss_uuid": ("protocols.wss", "uuid"),
    "ws_path": ("protocols.wss", "ws_path"),
    "xhttp_uuid": ("protocols.xhttp", "uuid"),
    "xhttp_path": ("protocols.xhttp", "xhttp_path"),
}

# Fields to skip during v1 migration (consumed but not carried forward)
_V1_SKIP = {"version", "xhttp_enabled"}


def _migrate_v1(data: dict[str, Any]) -> ServerCredentials:
    """Convert v1 flat format to v2 nested ServerCredentials."""
    panel = PanelConfig()
    server = ServerConfig()
    protocols: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for key, value in data.items():
        if value is None:
            continue
        if key in _V1_SKIP:
            continue

        if key in _V1_FIELD_MAP:
            section, field_name = _V1_FIELD_MAP[key]
            if section == "panel":
                setattr(panel, field_name, value)
            elif section == "server":
                setattr(server, field_name, value)
            elif section.startswith("protocols."):
                proto_name = section.split(".")[1]
                if proto_name not in protocols:
                    protocols[proto_name] = {}
                protocols[proto_name][field_name] = value
        else:
            # Unknown field — preserve in extra
            extra[key] = value

    # Convert protocol dicts to dataclasses
    typed_protocols: dict[str, Any] = {}
    if "reality" in protocols:
        typed_protocols["reality"] = RealityConfig(**protocols["reality"])
    if "wss" in protocols:
        typed_protocols["wss"] = WSSConfig(**protocols["wss"])
    if "xhttp" in protocols:
        typed_protocols["xhttp"] = XHTTPConfig(**protocols["xhttp"])

    return ServerCredentials(
        version=2,
        panel=panel,
        server=server,
        protocols=typed_protocols,
        clients=[],
        _extra=extra,
    )


def _load_v2(data: dict[str, Any]) -> ServerCredentials:
    """Load a v2 format YAML dict into ServerCredentials."""
    # Panel
    panel_data = data.get("panel", {})
    panel = _load_known_dataclass(
        panel_data,
        PanelConfig,
        {"username", "password", "web_base_path", "info_page_path", "port", "url"},
        defaults={"port": DEFAULT_PANEL_PORT, "url": ""},
    )

    # Server
    server_data = data.get("server", {})
    server = _load_known_dataclass(
        server_data,
        ServerConfig,
        {"ip", "domain", "sni", "scanned_sni", "hosted_page", "deployed_with", "warp", "geo_block", "decoy"},
        transforms={"hosted_page": bool, "warp": bool, "geo_block": bool},
        defaults={"hosted_page": False, "deployed_with": "", "warp": False, "geo_block": True, "decoy": ""},
    )

    # Protocols
    protocols: dict[str, Any] = {}
    protos_data = data.get("protocols", {})
    for proto_name, proto_data in protos_data.items():
        if proto_name == "reality":
            protocols["reality"] = _load_known_dataclass(
                proto_data,
                RealityConfig,
                {"uuid", "private_key", "public_key", "short_id", "encryption_key", "encryption_private_key"},
            )
        elif proto_name == "wss":
            protocols["wss"] = _load_known_dataclass(proto_data, WSSConfig, {"uuid", "ws_path"})
        elif proto_name == "xhttp":
            protocols["xhttp"] = _load_known_dataclass(proto_data, XHTTPConfig, {"uuid", "xhttp_path"})
        else:
            protocols[proto_name] = proto_data

    # Clients
    clients: list[ClientEntry] = []
    for c in data.get("clients", []):
        clients.append(
            _load_known_dataclass(
                c,
                ClientEntry,
                {"name", "added", "reality_uuid", "wss_uuid"},
                defaults={"name": "", "added": "", "reality_uuid": "", "wss_uuid": ""},
            )
        )

    # Relays
    relays: list[RelayEntry] = []
    for r in data.get("relays", []):
        relays.append(
            _load_known_dataclass(
                r,
                RelayEntry,
                {"ip", "name", "port", "added", "sni"},
                defaults={"ip": "", "name": "", "port": 443, "added": "", "sni": ""},
            )
        )

    # Extra fields
    known_top = {"version", "panel", "server", "protocols", "clients", "relays", "branding"}
    extra = {k: v for k, v in data.items() if k not in known_top}

    # Branding
    branding_data = data.get("branding", {})
    branding = _load_known_dataclass(
        branding_data,
        BrandingConfig,
        {"server_name", "icon", "color"},
        defaults={"server_name": "", "icon": "", "color": ""},
    )

    return ServerCredentials(
        version=2,
        panel=panel,
        server=server,
        protocols=protocols,
        clients=clients,
        relays=relays,
        branding=branding,
        _extra=extra,
    )


def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None values from a dict."""
    return {k: v for k, v in d.items() if v is not None}


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    """Serialize a dataclass and merge preserved unknown fields back in."""
    data = _strip_none({k: v for k, v in asdict(obj).items() if k != "_extra"})
    extra = getattr(obj, "_extra", {})
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in data:
                data[k] = v
    return data


def _load_known_dataclass(
    raw: Any,
    cls: type[Any],
    known_fields: set[str],
    *,
    defaults: dict[str, Any] | None = None,
    transforms: dict[str, Any] | None = None,
) -> Any:
    """Load known fields into a dataclass while preserving unknown nested ones."""
    if not isinstance(raw, dict):
        raw = {}
    defaults = defaults or {}
    transforms = transforms or {}
    values: dict[str, Any] = {}
    for field_name in known_fields:
        if field_name in raw:
            value = raw[field_name]
        elif field_name in defaults:
            value = defaults[field_name]
        else:
            continue
        if field_name in transforms:
            value = transforms[field_name](value)
        values[field_name] = value
    extra = {k: v for k, v in raw.items() if k not in known_fields}
    return cls(**values, _extra=extra)


def merge_clients_file(creds: ServerCredentials, clients_path: Path) -> bool:
    """Merge a separate -clients.yml file into the main credentials.

    Returns True if clients were merged (and the old file can be deleted).
    """
    if not clients_path.exists():
        return False
    raw = clients_path.read_text()
    if not raw.strip():
        return False
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        return False

    file_clients = data.get("clients", [])
    if not file_clients:
        return False

    # Build a set of existing client names to avoid duplicates
    existing_names = {c.name for c in creds.clients}

    for c in file_clients:
        name = c.get("name", "")
        if name and name not in existing_names:
            creds.clients.append(
                ClientEntry(
                    name=name,
                    added=c.get("added", ""),
                    reality_uuid=c.get("reality_uuid", ""),
                    wss_uuid=c.get("wss_uuid", ""),
                )
            )
            existing_names.add(name)

    return True
