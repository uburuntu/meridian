"""Tests for the pwa module (file generation, asset loading, upload)."""

from __future__ import annotations

import json
import subprocess

import pytest

from meridian.models import ProtocolURL, RelayURLSet
from meridian.pwa import generate_client_files, load_pwa_static_assets, upload_client_files, upload_pwa_assets

REALITY_URL = "vless://550e8400-e29b-41d4-a716-446655440000@198.51.100.1:443?security=reality#Test"


@pytest.fixture()
def protocol_urls() -> list[ProtocolURL]:
    return [
        ProtocolURL(key="reality", label="Primary", url=REALITY_URL, qr_b64="dGVzdA=="),
    ]


class TestGenerateClientFiles:
    def test_returns_four_files(self, protocol_urls: list[ProtocolURL]) -> None:
        files = generate_client_files(protocol_urls, "198.51.100.1")
        assert "index.html" in files
        assert "config.json" in files
        assert "manifest.webmanifest" in files
        assert "sub.txt" in files

    def test_config_json_has_client_name(self, protocol_urls: list[ProtocolURL]) -> None:
        files = generate_client_files(protocol_urls, "198.51.100.1", client_name="alice")
        config = json.loads(files["config.json"])
        assert config["client_name"] == "alice"

    def test_index_html_is_shell(self, protocol_urls: list[ProtocolURL]) -> None:
        files = generate_client_files(protocol_urls, "198.51.100.1")
        assert "app.js" in files["index.html"]
        assert "vless://" not in files["index.html"]

    def test_manifest_is_valid_json(self, protocol_urls: list[ProtocolURL]) -> None:
        files = generate_client_files(protocol_urls, "198.51.100.1")
        parsed = json.loads(files["manifest.webmanifest"])
        assert parsed["display"] == "standalone"

    def test_sub_txt_not_empty(self, protocol_urls: list[ProtocolURL]) -> None:
        files = generate_client_files(protocol_urls, "198.51.100.1")
        assert len(files["sub.txt"]) > 0

    def test_relay_entries_in_config(self, protocol_urls: list[ProtocolURL]) -> None:
        relays = [
            RelayURLSet(
                relay_ip="10.0.0.1",
                relay_name="test-relay",
                urls=[ProtocolURL(key="reality", label="Via relay", url=REALITY_URL)],
            ),
        ]
        files = generate_client_files(protocol_urls, "198.51.100.1", relay_entries=relays)
        config = json.loads(files["config.json"])
        assert len(config["relays"]) == 1
        assert config["relays"][0]["name"] == "test-relay"


class TestLoadPWAStaticAssets:
    def test_loads_all_assets(self) -> None:
        assets = load_pwa_static_assets()
        assert "app.js" in assets
        assert "styles.css" in assets
        assert "sw.js" in assets
        assert "icon.svg" in assets

    def test_assets_are_bytes(self) -> None:
        assets = load_pwa_static_assets()
        for name, content in assets.items():
            assert isinstance(content, bytes), f"{name} should be bytes"

    def test_icon_is_valid_svg(self) -> None:
        assets = load_pwa_static_assets()
        svg = assets["icon.svg"].decode("utf-8")
        assert "<svg" in svg

    def test_app_js_not_empty(self) -> None:
        assets = load_pwa_static_assets()
        assert len(assets["app.js"]) > 100

    def test_sw_js_has_cache_version(self) -> None:
        assets = load_pwa_static_assets()
        sw = assets["sw.js"].decode("utf-8")
        assert "CACHE_VERSION" in sw


# ---------------------------------------------------------------------------
# MockConnection (lightweight copy from provision/conftest.py for pwa tests)
# ---------------------------------------------------------------------------


class _MockConnection:
    """Minimal mock ServerConnection for upload tests."""

    def __init__(self) -> None:
        self._rules: list[tuple[str, subprocess.CompletedProcess[str]]] = []
        self._calls: list[str] = []
        self._default = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    def when(self, pattern: str, *, stdout: str = "", stderr: str = "", rc: int = 0) -> _MockConnection:
        self._rules.append((pattern, subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)))
        return self

    def run(self, command: str, timeout: int = 30, **kwargs: object) -> subprocess.CompletedProcess[str]:
        self._calls.append(command)
        for pattern, response in self._rules:
            if pattern in command:
                return response
        return self._default

    @property
    def calls(self) -> list[str]:
        return list(self._calls)

    def assert_called_with_pattern(self, pattern: str) -> None:
        assert any(pattern in c for c in self._calls), f"No call matching '{pattern}'. Calls: {self._calls}"


# ---------------------------------------------------------------------------
# TestUploadClientFiles
# ---------------------------------------------------------------------------


class TestUploadClientFiles:
    """Tests for upload_client_files() — per-client file deployment."""

    @pytest.fixture()
    def sample_files(self) -> dict[str, str]:
        return {
            "index.html": "<html>test</html>",
            "config.json": '{"version": 1}',
            "manifest.webmanifest": '{"display": "standalone"}',
            "sub.txt": "dmxlc3M6Ly8=",
        }

    def test_returns_true_on_success(self, sample_files: dict[str, str]) -> None:
        conn = _MockConnection()
        result = upload_client_files(conn, "550e8400-e29b-41d4-a716-446655440000", sample_files)
        assert result is True

    def test_returns_false_on_failure(self, sample_files: dict[str, str]) -> None:
        conn = _MockConnection()
        conn.when("printf", rc=1)
        result = upload_client_files(conn, "550e8400-e29b-41d4-a716-446655440000", sample_files)
        assert result is False

    def test_creates_directory_with_uuid(self, sample_files: dict[str, str]) -> None:
        conn = _MockConnection()
        upload_client_files(conn, "550e8400-e29b-41d4-a716-446655440000", sample_files)
        conn.assert_called_with_pattern("mkdir -p /var/www/private/550e8400")

    def test_uploads_all_files(self, sample_files: dict[str, str]) -> None:
        conn = _MockConnection()
        upload_client_files(conn, "550e8400-e29b-41d4-a716-446655440000", sample_files)
        # mkdir call + 4 file uploads = 5 total calls
        assert len(conn.calls) == 5

    def test_chown_caddy_on_files(self, sample_files: dict[str, str]) -> None:
        conn = _MockConnection()
        upload_client_files(conn, "550e8400-e29b-41d4-a716-446655440000", sample_files)
        # Each printf command includes chown caddy:caddy
        chown_calls = [c for c in conn.calls if "chown caddy:caddy" in c]
        # mkdir + chown on dir, plus 4 file uploads each with chown
        assert len(chown_calls) >= 5

    def test_filenames_are_shlex_quoted(self, sample_files: dict[str, str]) -> None:
        """Filenames in shell commands should be safely quoted."""
        conn = _MockConnection()
        upload_client_files(conn, "550e8400-e29b-41d4-a716-446655440000", sample_files)
        # All file upload commands should contain the filename
        for filename in sample_files:
            conn.assert_called_with_pattern(filename)


# ---------------------------------------------------------------------------
# TestUploadPWAAssets
# ---------------------------------------------------------------------------


class TestUploadPWAAssets:
    """Tests for upload_pwa_assets() — shared static asset deployment."""

    def test_returns_true_on_success(self) -> None:
        conn = _MockConnection()
        result = upload_pwa_assets(conn)
        assert result is True

    def test_returns_false_on_failure(self) -> None:
        conn = _MockConnection()
        # base64 -d write fails
        conn.when("base64 -d", rc=1)
        result = upload_pwa_assets(conn)
        assert result is False

    def test_creates_pwa_directory(self) -> None:
        conn = _MockConnection()
        upload_pwa_assets(conn)
        conn.assert_called_with_pattern("mkdir -p /var/www/private/pwa")

    def test_uploads_all_four_static_files(self) -> None:
        conn = _MockConnection()
        upload_pwa_assets(conn)
        # mkdir call + 4 file uploads = 5 total calls
        assert len(conn.calls) == 5

    def test_uses_base64_encoding(self) -> None:
        """Assets are base64-encoded for safe shell transport."""
        conn = _MockConnection()
        upload_pwa_assets(conn)
        # Each file upload should pipe base64 content through base64 -d
        b64_calls = [c for c in conn.calls if "base64 -d" in c]
        assert len(b64_calls) == 4

    def test_chown_caddy_on_assets(self) -> None:
        conn = _MockConnection()
        upload_pwa_assets(conn)
        chown_calls = [c for c in conn.calls if "chown caddy:caddy" in c]
        # mkdir chown + 4 file chowns = 5
        assert len(chown_calls) >= 5

    def test_deploys_to_correct_paths(self) -> None:
        """Each static file should be written to /var/www/private/pwa/."""
        conn = _MockConnection()
        upload_pwa_assets(conn)
        for fname in ("app.js", "styles.css", "sw.js", "icon.svg"):
            conn.assert_called_with_pattern(f"/var/www/private/pwa/{fname}")
