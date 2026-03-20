"""Structured credential management with YAML persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

import yaml


@dataclass
class ServerCredentials:
    """Typed access to proxy.yml credential fields.

    Replaces all grep/awk/tr YAML parsing from the bash CLI.
    Unknown fields in the YAML file are preserved on save (forward-compat).
    """

    panel_username: str = ""
    panel_password: str = ""
    panel_web_base_path: str = ""
    info_page_path: str = ""
    ws_path: str = ""
    reality_uuid: str = ""
    reality_private_key: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""
    reality_sni: str = ""
    wss_uuid: str = ""
    xhttp_uuid: str = ""
    xhttp_enabled: bool = False
    exit_ip: str = ""
    domain: str = ""
    scanned_sni: str = ""

    @classmethod
    def load(cls, path: Path) -> ServerCredentials:
        """Load from a proxy.yml file. Returns empty credentials if file doesn't exist."""
        if not path.exists():
            return cls()
        raw = path.read_text()
        if not raw.strip():
            return cls()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known and v is not None}
        return cls(**filtered)

    def save(self, path: Path) -> None:
        """Write to proxy.yml. Preserves unknown fields from existing file."""
        existing: dict = {}
        if path.exists():
            loaded = yaml.safe_load(path.read_text())
            if isinstance(loaded, dict):
                existing = loaded

        # Merge our fields into existing data (only non-empty values)
        for k, v in asdict(self).items():
            if isinstance(v, bool):
                existing[k] = v
            elif v:  # skip empty strings
                existing[k] = v

        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(yaml.dump(existing, default_flow_style=False, sort_keys=False))
        path.chmod(0o600)

    @property
    def has_domain(self) -> bool:
        return bool(self.domain)

    @property
    def has_credentials(self) -> bool:
        return bool(self.panel_username and self.panel_password)


def creds_path(creds_base: Path, server_ip: str) -> Path:
    """Return the proxy.yml path for a given server IP."""
    return creds_base / server_ip / "proxy.yml"


def clients_path(creds_base: Path, server_ip: str) -> Path:
    """Return the clients tracking file path for a given server IP."""
    return creds_base / server_ip / "proxy-clients.yml"
