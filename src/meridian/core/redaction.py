"""Secret redaction helpers for meridian-core JSON and diagnostics."""

from __future__ import annotations

import re
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

REDACTED = "[redacted]"

_SENSITIVE_KEY_PARTS = (
    "api_token",
    "apikey",
    "api_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "jwt",
    "password",
    "passwd",
    "secret",
    "private_key",
    "database_url",
    "db_url",
    "subscription_secret",
)

_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PEM_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_URL_USERINFO_RE = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@(?P<host>[^/\s]+)", re.I)
_ASSIGNMENT_RE = re.compile(
    r"(?P<key>\b(?:api[_-]?key|api[_-]?token|access[_-]?token|refresh[_-]?token|"
    r"auth[_-]?token|jwt|password|passwd|secret|private[_-]?key|database[_-]?url|db[_-]?url)\b)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value>[^\s,;]+)",
    re.I,
)


def is_sensitive_key(key: str) -> bool:
    """Return True when a mapping key should never expose its value."""
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_string(value: str) -> str:
    """Redact common secret forms inside free-form text."""
    redacted = _PEM_RE.sub(REDACTED, value)
    redacted = _JWT_RE.sub(REDACTED, redacted)
    redacted = _URL_USERINFO_RE.sub(lambda m: f"{m.group('scheme')}{REDACTED}@{m.group('host')}", redacted)
    return _ASSIGNMENT_RE.sub(lambda m: f"{m.group('key')}{m.group('sep')}{REDACTED}", redacted)


def redact(value: Any) -> Any:
    """Return a JSON-safe structure with obvious secrets removed."""
    if isinstance(value, BaseModel):
        return redact(value.model_dump(mode="json", by_alias=True))
    if is_dataclass(value):
        return {field.name: redact(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): REDACTED if is_sensitive_key(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_string(value)
    return value
