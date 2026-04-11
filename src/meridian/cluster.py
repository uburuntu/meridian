"""Fleet configuration with YAML persistence.

Replaces the per-server credentials.py with a single cluster-wide manifest.
Users/clients live in Remnawave's PostgreSQL — this file stores only
deployment topology and panel access.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


# StrEnum backport for Python 3.10 (stdlib StrEnum is 3.11+)
class StrEnum(str, Enum):
    """String enum compatible with Python 3.10+."""

    def __str__(self) -> str:
        return self.value


class ProtocolKey(StrEnum):
    """Protocol identifiers — single source of truth for string keys."""

    REALITY = "reality"
    XHTTP = "xhttp"
    WSS = "wss"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PanelConfig:
    """Remnawave panel connection details."""

    url: str = ""  # Panel HTTPS endpoint (e.g., https://panel.example.com)
    api_token: str = ""  # Remnawave JWT API token
    server_ip: str = ""  # IP where panel is deployed
    ssh_user: str = "root"
    ssh_port: int = 22
    secret_path: str = ""  # nginx reverse proxy path to panel
    sub_path: str = ""  # subscription endpoint path
    deployed_with: str = ""  # Meridian CLI version
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class NodeEntry:
    """A proxy node running Remnawave node + Xray."""

    ip: str = ""
    uuid: str = ""  # Remnawave node UUID
    name: str = ""  # friendly name (e.g., "finland")
    ssh_user: str = "root"
    ssh_port: int = 22
    sni: str = ""  # Reality SNI target
    domain: str = ""  # optional domain for WSS/XHTTP
    is_panel_host: bool = False  # panel runs on this node too
    deployed_with: str = ""  # Meridian CLI version
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class RelayEntry:
    """A Realm TCP relay forwarding traffic to an exit node."""

    ip: str = ""
    name: str = ""  # friendly name (e.g., "ru-moscow")
    port: int = 443  # relay listen port
    exit_node_ip: str = ""  # which node this relay forwards to
    host_uuids: dict[str, str] = field(default_factory=dict)  # protocol key → Remnawave host UUID
    sni: str = ""  # relay-specific SNI target
    ssh_user: str = "root"
    ssh_port: int = 22
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class BrandingConfig:
    """Server branding for connection pages."""

    server_name: str = ""  # display name (e.g., "Alice's VPN")
    icon: str = ""  # emoji or data URI
    color: str = ""  # palette name (ocean, sunset, forest, lavender, rose, slate)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class InboundRef:
    """Cached reference to a Remnawave inbound."""

    uuid: str = ""
    tag: str = ""
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ClusterConfig:
    """Fleet-wide configuration — the sole local state for Meridian 4.0.

    Stored at ~/.meridian/cluster.yml. One file replaces per-server proxy.yml.
    Client/user state lives in Remnawave's database, not here.
    """

    version: int = 1
    panel: PanelConfig = field(default_factory=PanelConfig)
    config_profile_uuid: str = ""
    config_profile_name: str = ""
    nodes: list[NodeEntry] = field(default_factory=list)
    relays: list[RelayEntry] = field(default_factory=list)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    inbounds: dict[str, InboundRef] = field(default_factory=dict)
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)

    # --- Persistence ---

    @classmethod
    def load(cls, path: Path | None = None) -> ClusterConfig:
        """Load from cluster.yml. Returns empty config if file doesn't exist."""
        if path is None:
            from meridian.config import CLUSTER_CONFIG

            path = CLUSTER_CONFIG
        if not path.exists():
            return cls()
        raw = path.read_text()
        if not raw.strip():
            return cls()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return cls()
        return _load_cluster(data)

    def save(self, path: Path | None = None) -> None:
        """Write to cluster.yml (atomic via tempfile+rename)."""
        if path is None:
            from meridian.config import CLUSTER_CONFIG

            path = CLUSTER_CONFIG

        out = _serialize_cluster(self)

        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Enforce dir permissions only for directories we create (not system temp dirs)
        try:
            path.parent.chmod(0o700)
        except PermissionError:
            pass

        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, yaml.dump(out, default_flow_style=False, sort_keys=False).encode())
            os.close(fd)
            fd = -1
            os.chmod(tmp, 0o600)
            os.rename(tmp, str(path))
        except BaseException:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # --- Convenience ---

    @property
    def is_configured(self) -> bool:
        """Whether the cluster has a panel configured."""
        return bool(self.panel.url and self.panel.api_token)

    @property
    def panel_node(self) -> NodeEntry | None:
        """Return the node that hosts the panel, if any."""
        for node in self.nodes:
            if node.is_panel_host:
                return node
        return None

    def find_node(self, query: str) -> NodeEntry | None:
        """Find a node by IP or name."""
        for node in self.nodes:
            if node.ip == query or node.name == query:
                return node
        return None

    def find_relay(self, query: str) -> RelayEntry | None:
        """Find a relay by IP or name."""
        for relay in self.relays:
            if relay.ip == query or relay.name == query:
                return relay
        return None

    def get_inbound(self, key: str | ProtocolKey) -> InboundRef | None:
        """Get a cached inbound reference by protocol key."""
        k = str(key)
        ref = self.inbounds.get(k)
        if ref is None:
            return None
        if isinstance(ref, dict):
            self.inbounds[k] = _load_dataclass(ref, InboundRef, _INBOUND_REF_FIELDS)
            return self.inbounds[k]
        return ref


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

_PANEL_FIELDS = {"url", "api_token", "server_ip", "ssh_user", "ssh_port", "secret_path", "sub_path", "deployed_with"}
_NODE_FIELDS = {"ip", "uuid", "name", "ssh_user", "ssh_port", "sni", "domain", "is_panel_host", "deployed_with"}
_RELAY_FIELDS = {"ip", "name", "port", "exit_node_ip", "host_uuids", "sni", "ssh_user", "ssh_port"}
_BRANDING_FIELDS = {"server_name", "icon", "color"}
_INBOUND_REF_FIELDS = {"uuid", "tag"}
_KNOWN_TOP = {"version", "panel", "config_profile_uuid", "config_profile_name", "nodes", "relays", "branding", "inbounds"}


def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys with None values."""
    return {k: v for k, v in d.items() if v is not None}


def _stringify_keys(d: dict[Any, Any]) -> dict[str, Any]:
    """Convert all dict keys to plain strings (handles StrEnum keys)."""
    return {str(k): v for k, v in d.items()}


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    """Serialize a dataclass, merging _extra fields back in."""
    data = _strip_none({k: v for k, v in asdict(obj).items() if k != "_extra"})
    # Convert any dict values with enum keys to plain strings
    for key, val in data.items():
        if isinstance(val, dict):
            data[key] = _stringify_keys(val)
    extra = getattr(obj, "_extra", {})
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in data:
                data[k] = v
    return data


def _serialize_cluster(cfg: ClusterConfig) -> dict[str, Any]:
    """Serialize ClusterConfig to a dict for YAML output."""
    out: dict[str, Any] = {"version": cfg.version}

    # Panel
    panel_dict = _serialize_dataclass(cfg.panel)
    # Remove default values to keep YAML clean
    if panel_dict.get("ssh_user") == "root":
        panel_dict.pop("ssh_user", None)
    if panel_dict.get("ssh_port") == 22:
        panel_dict.pop("ssh_port", None)
    if panel_dict:
        out["panel"] = panel_dict

    # Config profile
    if cfg.config_profile_uuid:
        out["config_profile_uuid"] = cfg.config_profile_uuid
    if cfg.config_profile_name:
        out["config_profile_name"] = cfg.config_profile_name

    # Nodes
    if cfg.nodes:
        nodes_out = []
        for node in cfg.nodes:
            d = _serialize_dataclass(node)
            if d.get("ssh_user") == "root":
                d.pop("ssh_user", None)
            if d.get("ssh_port") == 22:
                d.pop("ssh_port", None)
            if not d.get("is_panel_host"):
                d.pop("is_panel_host", None)
            nodes_out.append(d)
        out["nodes"] = nodes_out

    # Relays
    if cfg.relays:
        relays_out = []
        for relay in cfg.relays:
            d = _serialize_dataclass(relay)
            if d.get("ssh_user") == "root":
                d.pop("ssh_user", None)
            if d.get("ssh_port") == 22:
                d.pop("ssh_port", None)
            relays_out.append(d)
        out["relays"] = relays_out

    # Branding
    branding_dict = _serialize_dataclass(cfg.branding)
    for f in ("server_name", "icon", "color"):
        if branding_dict.get(f) == "":
            branding_dict.pop(f, None)
    if branding_dict:
        out["branding"] = branding_dict

    # Inbounds
    if cfg.inbounds:
        inbounds_out: dict[str, Any] = {}
        for key, ref in cfg.inbounds.items():
            str_key = str(key)  # ProtocolKey → plain string
            if hasattr(ref, "__dataclass_fields__"):
                inbounds_out[str_key] = _serialize_dataclass(ref)
            elif isinstance(ref, dict):
                inbounds_out[str_key] = _strip_none(ref)
            else:
                inbounds_out[str_key] = ref
        if inbounds_out:
            out["inbounds"] = inbounds_out

    # Extra fields (forward-compat)
    for k, v in cfg._extra.items():
        if k not in out:
            out[k] = v

    return out


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def _load_dataclass(
    raw: Any,
    cls: type[Any],
    known_fields: set[str],
    *,
    defaults: dict[str, Any] | None = None,
    transforms: dict[str, Any] | None = None,
) -> Any:
    """Load known fields into a dataclass, preserving unknown ones in _extra."""
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


def _load_cluster(data: dict[str, Any]) -> ClusterConfig:
    """Load a cluster config from parsed YAML."""
    # Panel
    panel = _load_dataclass(
        data.get("panel", {}),
        PanelConfig,
        _PANEL_FIELDS,
        defaults={"ssh_user": "root", "ssh_port": 22},
    )

    # Nodes
    nodes: list[NodeEntry] = []
    for n in data.get("nodes", []):
        nodes.append(
            _load_dataclass(
                n,
                NodeEntry,
                _NODE_FIELDS,
                defaults={"ssh_user": "root", "ssh_port": 22, "is_panel_host": False},
                transforms={"is_panel_host": bool},
            )
        )

    # Relays
    relays: list[RelayEntry] = []
    for r in data.get("relays", []):
        relays.append(
            _load_dataclass(
                r,
                RelayEntry,
                _RELAY_FIELDS,
                defaults={"ssh_user": "root", "ssh_port": 22, "port": 443},
            )
        )

    # Branding
    branding = _load_dataclass(
        data.get("branding", {}),
        BrandingConfig,
        _BRANDING_FIELDS,
        defaults={"server_name": "", "icon": "", "color": ""},
    )

    # Inbounds
    inbounds: dict[str, InboundRef] = {}
    for key, ref_data in data.get("inbounds", {}).items():
        inbounds[key] = _load_dataclass(ref_data, InboundRef, _INBOUND_REF_FIELDS)

    # Extra fields
    extra = {k: v for k, v in data.items() if k not in _KNOWN_TOP}

    return ClusterConfig(
        version=data.get("version", 1),
        panel=panel,
        config_profile_uuid=data.get("config_profile_uuid", ""),
        config_profile_name=data.get("config_profile_name", ""),
        nodes=nodes,
        relays=relays,
        branding=branding,
        inbounds=inbounds,
        _extra=extra,
    )
