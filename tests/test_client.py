"""Tests for client add/list/show/remove commands.

4.0: All client state lives in Remnawave's database.
Commands call the Remnawave REST API via MeridianPanel.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from meridian.cluster import ClusterConfig, PanelConfig
from meridian.commands.client import run_add, run_list, run_remove, run_show
from meridian.console import set_json_mode
from meridian.remnawave import RemnawaveError, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cluster(tmp_path: Path) -> ClusterConfig:
    """Create a minimal configured cluster."""
    cluster = ClusterConfig(
        panel=PanelConfig(
            url="https://198.51.100.1/panel",
            api_token="test-jwt-token",
            server_ip="198.51.100.1",
        ),
    )
    cluster.save(tmp_path / "cluster.yml")
    return cluster


def _make_user(name: str = "alice", status: str = "ACTIVE") -> User:
    return User(
        uuid="550e8400-e29b-41d4-a716-446655440000",
        short_uuid="abc123",
        username=name,
        status=status,
        used_traffic_bytes=1024 * 1024 * 100,  # 100 MB
        created_at="2026-04-01T12:00:00Z",
    )


def _make_panel_mock() -> MagicMock:
    """Create a mock MeridianPanel."""
    panel = MagicMock()
    panel.__enter__ = MagicMock(return_value=panel)
    panel.__exit__ = MagicMock(return_value=False)
    panel.create_user.return_value = _make_user()
    panel.get_user.return_value = _make_user()
    panel.list_users.return_value = [_make_user("alice"), _make_user("bob")]
    panel.delete_user.return_value = True
    panel.get_subscription_url.return_value = "https://198.51.100.1/api/sub/abc123"
    panel.ping.return_value = True
    return panel


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunAdd:
    def test_add_client_success(self, tmp_home: Path) -> None:
        """Adding a client calls panel.create_user and prints subscription URL."""
        _make_cluster(tmp_home)
        panel = _make_panel_mock()
        panel.get_user.return_value = None  # no existing user with this name

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_add(name="alice")

        panel.create_user.assert_called_once_with("alice", squad_uuids=None)

    def test_add_duplicate_client_fails(self, tmp_home: Path) -> None:
        """Adding a client that already exists should fail."""
        panel = _make_panel_mock()
        # User already exists
        panel.get_user.return_value = _make_user("alice")

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_add(name="alice")

        panel.create_user.assert_not_called()

    def test_add_client_empty_name_fails(self, tmp_home: Path) -> None:
        """Empty client name should fail."""
        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_add(name="")

    def test_add_client_no_cluster_fails(self, tmp_home: Path) -> None:
        """Adding a client without a configured cluster should fail."""
        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = ClusterConfig()  # unconfigured
            run_add(name="alice")


class TestRunShow:
    def test_show_existing_client(self, tmp_home: Path) -> None:
        """Showing an existing client prints subscription URL."""
        panel = _make_panel_mock()

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_show(name="alice")

        panel.get_user.assert_called_once_with("alice")

    def test_show_nonexistent_client_fails(self, tmp_home: Path) -> None:
        """Showing a non-existent client should fail."""
        panel = _make_panel_mock()
        panel.get_user.return_value = None

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_show(name="nonexistent")

    def test_show_json_redacts_subscription_url(self, tmp_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Legacy JSON renderer must still apply central redaction."""
        panel = _make_panel_mock()
        set_json_mode(True)
        try:
            with (
                patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
                patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            ):
                mock_load.return_value = _make_cluster(tmp_home)
                run_show(name="alice")
        finally:
            set_json_mode(False)

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "meridian.output/v1"
        assert payload["command"] == "client.show"
        assert payload["data"]["handoff"]["subscription_available"] is True
        assert payload["data"]["handoff"]["redacted"] is True
        assert "subscription_url" not in payload["data"]["client"]
        assert "abc123" not in json.dumps(payload)


class TestRunList:
    def test_list_clients(self, tmp_home: Path) -> None:
        """Listing clients calls panel.list_users."""
        panel = _make_panel_mock()

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_list()

        panel.list_users.assert_called_once()

    def test_list_empty_clients(self, tmp_home: Path) -> None:
        """Listing clients when none exist should still succeed."""
        panel = _make_panel_mock()
        panel.list_users.return_value = []

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_list()

    def test_list_json_outputs_envelope(self, tmp_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Client list JSON uses the standard output envelope."""
        panel = _make_panel_mock()
        set_json_mode(True)
        try:
            with (
                patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
                patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            ):
                mock_load.return_value = _make_cluster(tmp_home)
                run_list()
        finally:
            set_json_mode(False)

        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "meridian.output/v1"
        assert payload["command"] == "client.list"
        assert payload["data"]["summary"]["clients"] == 2
        assert payload["data"]["clients"][0]["traffic_used_bytes"] == 104857600


class TestRunRemove:
    def test_remove_existing_client(self, tmp_home: Path) -> None:
        """Removing a client calls panel.delete_user."""
        panel = _make_panel_mock()

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            patch("meridian.commands.client.confirm", return_value=True),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_remove(name="alice")

        panel.delete_user.assert_called_once()

    def test_remove_nonexistent_client_fails(self, tmp_home: Path) -> None:
        """Removing a non-existent client should fail."""
        panel = _make_panel_mock()
        panel.get_user.return_value = None

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_remove(name="nonexistent")

    def test_remove_cancelled_by_user(self, tmp_home: Path) -> None:
        """User declining confirmation should not delete."""
        panel = _make_panel_mock()

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            patch("meridian.commands.client.confirm", return_value=False),
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_remove(name="alice")

        panel.delete_user.assert_not_called()


class TestPanelAPIErrors:
    def test_api_error_on_add_shows_message(self, tmp_home: Path) -> None:
        """RemnawaveError during add should be caught and shown to user."""
        panel = _make_panel_mock()
        panel.get_user.return_value = None
        panel.create_user.side_effect = RemnawaveError("Panel unreachable")

        with (
            patch("meridian.commands._helpers.ClusterConfig.load") as mock_load,
            patch("meridian.commands._helpers.MeridianPanel", return_value=panel),
            pytest.raises(typer.Exit),
        ):
            mock_load.return_value = _make_cluster(tmp_home)
            run_add(name="alice")
