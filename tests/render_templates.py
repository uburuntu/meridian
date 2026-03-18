"""Render all Jinja2 templates with mock variables to catch undefined vars and syntax errors."""
import sys
from jinja2 import Environment, FileSystemLoader, Undefined
import re


# Permissive undefined that doesn't crash on missing vars or filters
class MockUndefined(Undefined):
    def __str__(self):
        return ""

    def __bool__(self):
        return False

    def __iter__(self):
        return iter([])

    def __getattr__(self, name):
        return MockUndefined()

    def __call__(self, *args, **kwargs):
        return MockUndefined()


# Mock Ansible filters that templates use
def mock_bool(value):
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return bool(value)


def mock_default(value, default_value="", boolean=False):
    if value is None or isinstance(value, Undefined):
        return default_value
    if boolean and not value:
        return default_value
    return value


def mock_regex_search(value, pattern, *args):
    match = re.search(pattern, str(value))
    if match:
        if match.groups():
            return list(match.groups())
        return match.group(0)
    return None


def mock_hash(value, method="sha1"):
    return "a1b2c3d4e5f6"


def mock_int(value, default=0, base=10):
    try:
        return int(str(value), base)
    except (ValueError, TypeError):
        return default


# Mock object for registered task results (e.g., qrencode output)
class MockResult:
    def __init__(self, stdout="dGVzdA=="):
        self.stdout = stdout


MOCK_VARS = {
    "domain": "example.com",
    "email": "",
    "domain_mode": True,
    "relay_mode": False,
    "exit_mode": False,
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
    "reality_direct_port": 8444,
    "server_public_ip": "1.2.3.4",
    "inventory_hostname": "proxy",
    "ansible_host": "1.2.3.4",
    "ansible_date_time": {"iso8601": "2026-01-01T00:00:00Z", "year": "2026"},
    "threexui_version": "2.8.11",
    "utls_fingerprint": "chrome",
    "decoy_site_title": "Westbridge Partners",
    "decoy_site_tagline": "Strategic advisory for modern enterprises",
    "relay_inbound_port": 443,
    "exit_ip": "1.2.3.4",
    "xhttp_mode": "packet-up",
    "xhttp_path": "/",
    "credentials_dir": "/tmp/credentials",
    "credentials_file": "/tmp/credentials/proxy.yml",
    "vless_reality_url": "vless://test-uuid@1.2.3.4:443?security=reality#Test",
    "vless_wss_url": "vless://test-uuid@example.com:443?security=tls#Test",
    "vless_direct_url": "vless://test-uuid@1.2.3.4:8444?security=reality#Test",
    "vless_relay_url": "vless://test-uuid@5.6.7.8:443?security=none#Test",
    "reality_qr_b64": MockResult(),
    "wss_qr_b64": MockResult(),
    "reality_qr_b64_local": MockResult(),
    "wss_qr_b64_local": MockResult(),
    "relay_qr_b64": MockResult(),
    "reality_qr_terminal": MockResult(stdout="QR_CODE_HERE"),
    "wss_qr_terminal": MockResult(stdout="QR_CODE_HERE"),
    "port_443_check": MockResult(stdout="LISTEN 0 4096 *:443"),
    "port_direct_check": MockResult(stdout=""),
    "reality_uuid": "test-uuid",
    "reality_public_key": "test-pubkey",
    "reality_short_id": "abcd1234",
    "xhttp_uuid": "test-xhttp-uuid",
}

TEMPLATES = [
    ("roles/decoy_site/templates", "index.html.j2"),
    ("roles/decoy_site/templates", "connection-info.html.j2"),
    ("roles/output/templates", "connection-info.html.j2"),
    ("roles/output/templates", "connection-summary.txt.j2"),
    ("roles/output_relay/templates", "connection-info.html.j2"),
    ("roles/output_relay/templates", "connection-summary.txt.j2"),
    ("roles/xray/templates", "docker-compose.yml.j2"),
    ("roles/caddy/templates", "Caddyfile.j2"),
    ("roles/haproxy/templates", "haproxy.cfg.j2"),
]

failed = False
for tpl_dir, tpl_name in TEMPLATES:
    try:
        env = Environment(
            loader=FileSystemLoader(tpl_dir),
            undefined=MockUndefined,
        )
        # Register Ansible-compatible filters
        env.filters["bool"] = mock_bool
        env.filters["default"] = mock_default
        env.filters["d"] = mock_default
        env.filters["regex_search"] = mock_regex_search
        env.filters["hash"] = mock_hash
        env.filters["int"] = mock_int
        env.filters["trim"] = lambda x: str(x).strip()
        env.filters["replace"] = lambda x, old, new: str(x).replace(old, new)
        env.filters["length"] = len
        env.filters["lower"] = lambda x: str(x).lower()
        env.filters["upper"] = lambda x: str(x).upper()
        env.filters["to_json"] = lambda x: str(x)
        # Register Ansible tests
        env.tests["defined"] = lambda x: not isinstance(x, Undefined)
        env.tests["undefined"] = lambda x: isinstance(x, Undefined)
        env.tests["none"] = lambda x: x is None
        env.tests["succeeded"] = lambda x: True
        env.tests["failed"] = lambda x: False

        t = env.get_template(tpl_name)
        result = t.render(**MOCK_VARS)
        if len(result) < 10:
            print(f"WARN: {tpl_dir}/{tpl_name} — only {len(result)} chars")
        else:
            print(f"  OK: {tpl_dir}/{tpl_name} ({len(result)} chars)")
    except Exception as e:
        print(f"FAIL: {tpl_dir}/{tpl_name} — {e}")
        failed = True

sys.exit(1 if failed else 0)
