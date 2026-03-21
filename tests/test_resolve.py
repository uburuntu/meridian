"""Tests for server resolution logic — all 5+ resolution paths."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from meridian.commands.resolve import resolve_server
from meridian.config import CREDS_BASE, SERVER_CREDS_DIR
from meridian.servers import ServerEntry, ServerRegistry


class TestExplicitIP:
    """Path 1: explicit_ip argument takes highest priority."""

    def test_explicit_ip_returns_resolved(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg, explicit_ip="1.2.3.4")
        assert result.ip == "1.2.3.4"
        assert result.user == "root"  # default
        assert result.local_mode is False

    def test_explicit_ip_with_user(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg, explicit_ip="1.2.3.4", user="ubuntu")
        assert result.user == "ubuntu"

    def test_explicit_ip_picks_user_from_registry(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("1.2.3.4", "ubuntu", "mybox"))
        result = resolve_server(reg, explicit_ip="1.2.3.4")
        assert result.user == "ubuntu"  # resolved from registry

    def test_explicit_user_overrides_registry(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("1.2.3.4", "ubuntu", "mybox"))
        result = resolve_server(reg, explicit_ip="1.2.3.4", user="admin")
        assert result.user == "admin"  # explicit overrides

    def test_explicit_ip_creds_dir(self, tmp_home: Path, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg, explicit_ip="5.6.7.8")
        assert result.creds_dir == CREDS_BASE / "5.6.7.8"


class TestServerFlag:
    """Path 2: --server flag (by name or IP)."""

    def test_server_by_name(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("1.2.3.4", "root", "mybox"))
        result = resolve_server(reg, requested_server="mybox")
        assert result.ip == "1.2.3.4"
        assert result.user == "root"

    def test_server_by_ip(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("1.2.3.4", "ubuntu", "mybox"))
        result = resolve_server(reg, requested_server="1.2.3.4")
        assert result.ip == "1.2.3.4"
        assert result.user == "ubuntu"

    def test_server_ip_not_in_registry(self, servers_file: Path) -> None:
        """Bare IP via --server should still resolve even if not registered."""
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg, requested_server="9.8.7.6")
        assert result.ip == "9.8.7.6"
        assert result.user == "root"

    def test_server_name_not_found_exits(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        with pytest.raises(typer.Exit) as exc_info:
            resolve_server(reg, requested_server="nonexistent")
        assert exc_info.value.exit_code == 1

    def test_server_by_name_inherits_user(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("1.2.3.4", "deploy", "prod"))
        result = resolve_server(reg, requested_server="prod")
        assert result.user == "deploy"


class TestSingleServerAutoSelect:
    """Path 4: single registered server auto-selected."""

    def test_single_server_auto_select(self, servers_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patch _detect_local_mode_from_creds to return None (not on server)
        monkeypatch.setattr(
            "meridian.commands.resolve._detect_local_mode_from_creds",
            lambda: None,
        )
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("10.20.30.40", "root", "only-one"))
        result = resolve_server(reg)
        assert result.ip == "10.20.30.40"
        assert result.user == "root"


class TestMultipleServers:
    """Path 5: multiple servers registered, no selection."""

    def test_multiple_servers_fail(self, servers_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "meridian.commands.resolve._detect_local_mode_from_creds",
            lambda: None,
        )
        reg = ServerRegistry(servers_file)
        reg.add(ServerEntry("1.2.3.4", "root", "server1"))
        reg.add(ServerEntry("5.6.7.8", "root", "server2"))
        with pytest.raises(typer.Exit) as exc_info:
            resolve_server(reg)
        assert exc_info.value.exit_code == 1


class TestNoServers:
    """Path 6: empty registry, no explicit IP."""

    def test_no_servers_fail(self, servers_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "meridian.commands.resolve._detect_local_mode_from_creds",
            lambda: None,
        )
        reg = ServerRegistry(servers_file)
        with pytest.raises(typer.Exit) as exc_info:
            resolve_server(reg)
        assert exc_info.value.exit_code == 1


class TestLocalMode:
    """Path 3: running on the server itself as root."""

    def test_local_mode_detection(self, servers_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "meridian.commands.resolve._detect_local_mode_from_creds",
            lambda: "10.0.0.1",
        )
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg)
        assert result.ip == "10.0.0.1"
        assert result.local_mode is True
        assert result.creds_dir == SERVER_CREDS_DIR


class TestResolvedServer:
    """Test ResolvedServer dataclass properties."""

    def test_frozen(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg, explicit_ip="1.2.3.4")
        with pytest.raises(AttributeError):
            result.ip = "changed"  # type: ignore[misc]

    def test_conn_created(self, servers_file: Path) -> None:
        reg = ServerRegistry(servers_file)
        result = resolve_server(reg, explicit_ip="1.2.3.4", user="ubuntu")
        assert result.conn.ip == "1.2.3.4"
        assert result.conn.user == "ubuntu"
        assert result.conn.local_mode is False
