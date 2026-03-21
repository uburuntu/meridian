"""Pytest version of template rendering tests.

Auto-discovers all .j2 templates under src/meridian/templates/ and
renders each with a mock variable context. Failures are reported as proper
pytest assertions (one test case per template file).

The standalone render_templates.py script is kept for CI use — this file
is the pytest counterpart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, Undefined

# ---------------------------------------------------------------------------
# Mock infrastructure (mirrors render_templates.py)
# ---------------------------------------------------------------------------


class MockUndefined(Undefined):
    """Permissive undefined that never crashes on missing vars or filters."""

    def __str__(self) -> str:
        return ""

    def __bool__(self) -> bool:
        return False

    def __iter__(self):  # type: ignore[override]
        return iter([])

    def __getattr__(self, name: str) -> "MockUndefined":
        return MockUndefined()

    def __call__(self, *args: object, **kwargs: object) -> "MockUndefined":
        return MockUndefined()


def _mock_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return bool(value)


def _mock_default(value: object, default_value: object = "", boolean: bool = False) -> object:
    if value is None or isinstance(value, Undefined):
        return default_value
    if boolean and not value:
        return default_value
    return value


def _mock_regex_search(value: object, pattern: str, *args: object) -> object:
    match = re.search(pattern, str(value))
    if match:
        if match.groups():
            return list(match.groups())
        return match.group(0)
    return None


def _mock_hash(value: object, method: str = "sha1") -> str:
    return "a1b2c3d4e5f6"


def _mock_int(value: object, default: int = 0, base: int = 10) -> int:
    try:
        return int(str(value), base)
    except (ValueError, TypeError):
        return default


class MockResult:
    """Mock for registered task results (e.g., qrencode output)."""

    def __init__(self, stdout: str = "dGVzdA==") -> None:
        self.stdout = stdout


MOCK_VARS: dict[str, object] = {
    "domain": "example.com",
    "email": "",
    "domain_mode": True,
    "panel_internal_port": 2053,
    "panel_external_port": 12345,
    "panel_web_base_path": "testpath123",
    "panel_username": "testuser",
    "panel_password": "testpass",
    "info_page_path": "testinfo456",
    "ws_path": "testws789",
    "caddy_internal_port": 8443,
    "wss_internal_port": 28000,
    "haproxy_reality_backend_port": 10443,
    "reality_sni": "www.microsoft.com",
    "reality_dest": "www.microsoft.com:443",
    "server_public_ip": "1.2.3.4",
    "inventory_hostname": "proxy",
    "generated_at": {"iso8601": "2026-01-01T00:00:00Z", "year": "2026"},
    "threexui_version": "2.8.11",
    "utls_fingerprint": "chrome",
    "xhttp_mode": "packet-up",
    "xhttp_path": "/",
    "credentials_dir": "/tmp/credentials",
    "credentials_file": "/tmp/credentials/proxy.yml",
    "vless_reality_url": "vless://test-uuid@1.2.3.4:443?security=reality#Test",
    "vless_wss_url": "vless://test-uuid@example.com:443?security=tls#Test",
    "reality_qr_b64": MockResult(),
    "wss_qr_b64": MockResult(),
    "reality_qr_b64_local": MockResult(),
    "wss_qr_b64_local": MockResult(),
    "reality_qr_terminal": MockResult(stdout="QR_CODE_HERE"),
    "wss_qr_terminal": MockResult(stdout="QR_CODE_HERE"),
    "port_443_check": MockResult(stdout="LISTEN 0 4096 *:443"),
    "reality_uuid": "test-uuid",
    "reality_public_key": "test-pubkey",
    "reality_short_id": "abcd1234",
    "xhttp_enabled": True,
    "xhttp_inbound_port": 34567,
    "vless_xhttp_url": "vless://test-uuid@1.2.3.4:34567?security=reality&type=xhttp#Test-XHTTP",
    "xhttp_qr_terminal": MockResult(stdout="QR_CODE_HERE"),
    "xhttp_qr_b64_local": MockResult(),
    "xhttp_qr_b64": MockResult(),
    "port_xhttp_check": MockResult(stdout="LISTEN 0 4096 *:34567"),
    "client_name": "default",
    "first_client_name": "default",
    "is_server_hosted": True,
}


def _make_env(template_dir: Path) -> Environment:
    """Create a Jinja2 Environment with template filters and mocks."""
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=MockUndefined,
    )
    env.filters["bool"] = _mock_bool
    env.filters["default"] = _mock_default
    env.filters["d"] = _mock_default
    env.filters["regex_search"] = _mock_regex_search
    env.filters["hash"] = _mock_hash
    env.filters["int"] = _mock_int
    env.filters["trim"] = lambda x: str(x).strip()
    env.filters["replace"] = lambda x, old, new: str(x).replace(old, new)
    env.filters["length"] = len
    env.filters["lower"] = lambda x: str(x).lower()
    env.filters["upper"] = lambda x: str(x).upper()
    env.filters["to_json"] = lambda x: str(x)
    env.tests["defined"] = lambda x: not isinstance(x, Undefined)
    env.tests["undefined"] = lambda x: isinstance(x, Undefined)
    env.tests["none"] = lambda x: x is None
    env.tests["succeeded"] = lambda x: True
    env.tests["failed"] = lambda x: False
    return env


# ---------------------------------------------------------------------------
# Template discovery
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "meridian" / "templates"
_TEMPLATES = list(_TEMPLATES_DIR.glob("*.j2"))


def _template_id(p: Path) -> str:
    """Human-readable pytest ID: <filename>.j2"""
    return p.name


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template_path",
    sorted(_TEMPLATES),
    ids=[_template_id(p) for p in sorted(_TEMPLATES)],
)
def test_template_renders(template_path: Path) -> None:
    """Each .j2 template must render without exceptions using mock variables."""
    env = _make_env(template_path.parent)
    template = env.get_template(template_path.name)
    result = template.render(**MOCK_VARS)
    # Sanity check: non-trivial output
    assert len(result) >= 1, f"Template rendered empty output: {template_path}"


def test_templates_discovered() -> None:
    """Sanity check that template auto-discovery finds at least a few templates."""
    assert len(_TEMPLATES) >= 1, f"Expected at least 1 template under {_TEMPLATES_DIR}, found {len(_TEMPLATES)}"
