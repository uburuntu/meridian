"""Tests for relay node functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from meridian.credentials import RelayEntry, ServerCredentials
from meridian.models import ProtocolURL, RelayURLSet

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_proxy_with_relays(creds_dir: Path) -> Path:
    """Write a v2 proxy.yml with relay entries."""
    content = """\
version: 2
panel_configured: true
panel:
  username: admin
  password: "s3cret!pass"
  web_base_path: abc123
  info_page_path: info456
  port: 2053
server:
  ip: 5.6.7.8
  sni: www.microsoft.com
  hosted_page: true
protocols:
  reality:
    uuid: 550e8400-e29b-41d4-a716-446655440000
    private_key: WBNp7SHzGMaqp6ohXMfJHUyBMWHoeHMflVPaaxdtRHo
    public_key: K6JYbz4MflVPaaxdtRHoWBNp7SHzGMaqp6ohXMfJHUy
    short_id: abcd1234
  wss:
    uuid: 660e8400-e29b-41d4-a716-446655440001
    ws_path: ws789
  xhttp:
    xhttp_path: xhttp123
clients:
  - name: default
    added: "2026-01-01T00:00:00Z"
    reality_uuid: 550e8400-e29b-41d4-a716-446655440000
    wss_uuid: 660e8400-e29b-41d4-a716-446655440001
relays:
  - ip: 1.2.3.4
    name: ru-moscow
    port: 443
    added: "2026-03-22T12:00:00Z"
  - ip: 10.20.30.40
    name: ru-spb
    port: 443
    added: "2026-03-22T13:00:00Z"
"""
    proxy = creds_dir / "proxy.yml"
    proxy.write_text(content)
    proxy.chmod(0o600)
    return proxy


# ---------------------------------------------------------------------------
# Credential tests
# ---------------------------------------------------------------------------


class TestRelayEntry:
    def test_relay_entry_defaults(self) -> None:
        entry = RelayEntry()
        assert entry.ip == ""
        assert entry.name == ""
        assert entry.port == 443
        assert entry.added == ""

    def test_relay_entry_with_values(self) -> None:
        entry = RelayEntry(ip="1.2.3.4", name="ru-moscow", port=443, added="2026-01-01T00:00:00Z")
        assert entry.ip == "1.2.3.4"
        assert entry.name == "ru-moscow"
        assert entry.port == 443


class TestCredentialsWithRelays:
    def test_load_with_relays(self, sample_proxy_with_relays: Path) -> None:
        creds = ServerCredentials.load(sample_proxy_with_relays)
        assert len(creds.relays) == 2
        assert creds.relays[0].ip == "1.2.3.4"
        assert creds.relays[0].name == "ru-moscow"
        assert creds.relays[1].ip == "10.20.30.40"
        assert creds.relays[1].name == "ru-spb"

    def test_load_without_relays(self, sample_proxy_yml: Path) -> None:
        """Old credentials without relays should have empty relay list."""
        creds = ServerCredentials.load(sample_proxy_yml)
        assert creds.relays == []

    def test_save_and_load_relays_roundtrip(self, tmp_path: Path) -> None:
        creds = ServerCredentials()
        creds.relays = [
            RelayEntry(ip="1.2.3.4", name="test-relay", port=443, added="2026-01-01T00:00:00Z"),
        ]
        path = tmp_path / "proxy.yml"
        creds.save(path)

        loaded = ServerCredentials.load(path)
        assert len(loaded.relays) == 1
        assert loaded.relays[0].ip == "1.2.3.4"
        assert loaded.relays[0].name == "test-relay"
        assert loaded.relays[0].port == 443

    def test_add_and_remove_relay(self) -> None:
        creds = ServerCredentials()
        relay = RelayEntry(ip="1.2.3.4", name="relay1")
        creds.relays.append(relay)
        assert len(creds.relays) == 1

        creds.relays = [r for r in creds.relays if r.ip != "1.2.3.4"]
        assert len(creds.relays) == 0

    def test_save_without_relays_omits_section(self, tmp_path: Path) -> None:
        """Credentials with no relays should not have a relays key in YAML."""
        creds = ServerCredentials()
        path = tmp_path / "proxy.yml"
        creds.save(path)

        raw = path.read_text()
        assert "relays" not in raw


# ---------------------------------------------------------------------------
# URL generation tests
# ---------------------------------------------------------------------------


class TestBuildRelayUrls:
    def test_build_relay_urls(self, sample_proxy_with_relays: Path) -> None:
        from meridian.urls import build_relay_urls

        creds = ServerCredentials.load(sample_proxy_with_relays)
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        result = build_relay_urls("alice", uuid, creds, "1.2.3.4", "ru-moscow")

        assert isinstance(result, RelayURLSet)
        assert result.relay_ip == "1.2.3.4"
        assert result.relay_name == "ru-moscow"
        assert len(result.urls) == 1
        assert result.urls[0].key == "reality"

        # URL should contain relay IP, not exit IP
        url = result.urls[0].url
        assert "@1.2.3.4:" in url
        assert "@5.6.7.8:" not in url

        # URL should contain exit's Reality parameters
        assert "K6JYbz4MflVPaaxdtRHoWBNp7SHzGMaqp6ohXMfJHUy" in url  # public key
        assert "abcd1234" in url  # short ID
        assert "www.microsoft.com" in url  # SNI
        assert uuid in url

        # Fragment should include relay identifier
        assert "via-ru-moscow" in url

    def test_build_relay_urls_no_name(self, sample_proxy_with_relays: Path) -> None:
        from meridian.urls import build_relay_urls

        creds = ServerCredentials.load(sample_proxy_with_relays)
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        result = build_relay_urls("bob", uuid, creds, "9.9.9.9")
        assert "via-9.9.9.9" in result.urls[0].url

    def test_build_all_relay_urls(self, sample_proxy_with_relays: Path) -> None:
        from meridian.urls import build_all_relay_urls

        creds = ServerCredentials.load(sample_proxy_with_relays)
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        results = build_all_relay_urls("alice", uuid, creds)
        assert len(results) == 2
        assert results[0].relay_ip == "1.2.3.4"
        assert results[1].relay_ip == "10.20.30.40"

    def test_build_all_relay_urls_no_relays(self, sample_proxy_yml: Path) -> None:
        from meridian.urls import build_all_relay_urls

        creds = ServerCredentials.load(sample_proxy_yml)
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        results = build_all_relay_urls("alice", uuid, creds)
        assert results == []


# ---------------------------------------------------------------------------
# RelayURLSet model tests
# ---------------------------------------------------------------------------


class TestRelayURLSet:
    def test_frozen(self) -> None:
        url_set = RelayURLSet(
            relay_ip="1.2.3.4",
            relay_name="test",
            urls=[ProtocolURL(key="reality", label="Primary", url="vless://test@1.2.3.4:443")],
        )
        assert url_set.relay_ip == "1.2.3.4"
        assert url_set.relay_name == "test"
        assert len(url_set.urls) == 1


# ---------------------------------------------------------------------------
# Provisioner tests
# ---------------------------------------------------------------------------


class TestRelayProvisioner:
    def test_build_relay_steps(self) -> None:
        from meridian.provision.relay import RelayContext, build_relay_steps

        ctx = RelayContext(relay_ip="1.2.3.4", exit_ip="5.6.7.8")
        steps = build_relay_steps(ctx)
        assert len(steps) == 6
        names = [s.name for s in steps]
        assert "Install relay packages" in names
        assert "Enable BBR congestion control" in names
        assert "Configure relay firewall" in names
        assert "Install Realm TCP relay" in names
        assert "Configure Realm relay" in names
        assert "Verify relay connectivity" in names

    def test_relay_context_defaults(self) -> None:
        from meridian.provision.relay import RelayContext

        ctx = RelayContext(relay_ip="1.2.3.4", exit_ip="5.6.7.8")
        assert ctx.exit_port == 443
        assert ctx.listen_port == 443
        assert ctx.user == "root"

    def test_configure_realm_generates_correct_config(self) -> None:
        """Verify ConfigureRealm generates valid TOML-like config content."""
        from meridian.provision.relay import ConfigureRealm, RelayContext

        step = ConfigureRealm()
        ctx = RelayContext(relay_ip="1.2.3.4", exit_ip="5.6.7.8", listen_port=443)

        # Mock ServerConnection
        conn = MagicMock()
        conn.run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))

        result = step.run(conn, ctx)
        assert result.status == "changed"

        # Check that config was written with correct exit IP and port
        calls = [str(c) for c in conn.run.call_args_list]
        config_call = [c for c in calls if "realm.toml" in c]
        assert len(config_call) > 0

    def test_verify_relay_checks_service_and_tcp(self) -> None:
        from meridian.provision.relay import RelayContext, VerifyRelay

        step = VerifyRelay()
        ctx = RelayContext(relay_ip="1.2.3.4", exit_ip="5.6.7.8")

        # Mock: service active, TCP reachable
        conn = MagicMock()
        conn.run = MagicMock(
            side_effect=[
                MagicMock(returncode=0, stdout="active\n", stderr=""),  # systemctl is-active
                MagicMock(returncode=0, stdout="", stderr=""),  # TCP test
            ]
        )

        result = step.run(conn, ctx)
        assert result.status == "ok"

    def test_verify_relay_fails_on_inactive_service(self) -> None:
        from meridian.provision.relay import RelayContext, VerifyRelay

        step = VerifyRelay()
        ctx = RelayContext(relay_ip="1.2.3.4", exit_ip="5.6.7.8")

        conn = MagicMock()
        conn.run = MagicMock(
            side_effect=[
                MagicMock(returncode=3, stdout="inactive\n", stderr=""),  # systemctl is-active
                MagicMock(returncode=0, stdout="", stderr=""),  # journalctl
            ]
        )

        result = step.run(conn, ctx)
        assert result.status == "failed"


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestRelayCLI:
    def test_relay_help(self) -> None:
        from typer.testing import CliRunner

        from meridian.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["relay", "--help"])
        assert result.exit_code == 0
        assert "deploy" in result.output
        assert "list" in result.output
        assert "remove" in result.output
        assert "check" in result.output

    def test_relay_deploy_help(self) -> None:
        from typer.testing import CliRunner

        from meridian.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["relay", "deploy", "--help"])
        assert result.exit_code == 0
        assert "--exit" in result.output
        assert "RELAY_IP" in result.output


# ---------------------------------------------------------------------------
# Rendering tests
# ---------------------------------------------------------------------------


class TestRenderingWithRelays:
    def test_save_connection_text_with_relays(self, tmp_path: Path) -> None:
        from meridian.render import save_connection_text

        protocol_urls = [
            ProtocolURL(key="reality", label="Primary", url="vless://uuid@5.6.7.8:443?security=reality#alice"),
        ]
        relay_entries = [
            RelayURLSet(
                relay_ip="1.2.3.4",
                relay_name="ru-moscow",
                urls=[ProtocolURL(key="reality", label="Primary (via relay)", url="vless://uuid@1.2.3.4:443?security=reality#alice-via-ru-moscow")],
            ),
        ]

        dest = tmp_path / "test.txt"
        save_connection_text(protocol_urls, dest, "5.6.7.8", relay_entries=relay_entries)

        content = dest.read_text()
        assert "Recommended" in content
        assert "via relay" in content
        assert "1.2.3.4" in content
        assert "Backup" in content

    def test_save_connection_text_without_relays(self, tmp_path: Path) -> None:
        from meridian.render import save_connection_text

        protocol_urls = [
            ProtocolURL(key="reality", label="Primary", url="vless://uuid@5.6.7.8:443?security=reality#alice"),
        ]

        dest = tmp_path / "test.txt"
        save_connection_text(protocol_urls, dest, "5.6.7.8")

        content = dest.read_text()
        assert "via relay" not in content
        assert "Backup: direct" not in content

    def test_save_connection_html_with_relays_fallback(self, tmp_path: Path) -> None:
        """Test HTML output with relay entries includes relay section."""
        from meridian.render import save_connection_html

        protocol_urls = [
            ProtocolURL(key="reality", label="Primary", url="vless://uuid@5.6.7.8:443?security=reality#alice"),
        ]
        relay_entries = [
            RelayURLSet(
                relay_ip="1.2.3.4",
                relay_name="ru-moscow",
                urls=[ProtocolURL(key="reality", label="Primary (via relay)", url="vless://uuid@1.2.3.4:443?security=reality#alice-via-ru-moscow")],
            ),
        ]

        dest = tmp_path / "test.html"
        save_connection_html(protocol_urls, dest, "5.6.7.8", relay_entries=relay_entries)

        content = dest.read_text()
        assert "Recommended" in content
        assert "BACKUP" in content
        assert "1.2.3.4" in content
        assert "ru-moscow" in content

    def test_save_connection_html_without_relays_unchanged(self, tmp_path: Path) -> None:
        """Without relays, HTML output should not contain relay sections."""
        from meridian.render import save_connection_html

        protocol_urls = [
            ProtocolURL(key="reality", label="Primary", url="vless://uuid@5.6.7.8:443?security=reality#alice"),
        ]

        dest = tmp_path / "test.html"
        save_connection_html(protocol_urls, dest, "5.6.7.8")

        content = dest.read_text()
        assert "BACKUP (DIRECT)" not in content
        assert "via relay" not in content
