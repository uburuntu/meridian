"""Tests for cluster.yml schema migration framework."""

from __future__ import annotations

from meridian.migrations import CURRENT_VERSION, migrate


class TestMigrations:
    def test_current_version_unchanged(self) -> None:
        data = {"version": CURRENT_VERSION, "panel": {"url": "https://test"}}
        result = migrate(data)
        assert result["version"] == CURRENT_VERSION
        assert result["panel"]["url"] == "https://test"

    def test_future_version_unchanged(self) -> None:
        data = {"version": 99, "panel": {"url": "https://test"}}
        result = migrate(data)
        assert result["version"] == 99

    def test_missing_version_treated_as_v1_and_migrated(self) -> None:
        data = {"panel": {"url": "https://test"}}
        result = migrate(data)
        assert result["version"] == CURRENT_VERSION
        assert result["panel"]["url"] == "https://test"
        # v1→v2 does NOT add subscription_page (legacy clusters unmanaged)
        assert "subscription_page" not in result

    def test_v1_migrates_to_v2(self) -> None:
        data = {"version": 1, "panel": {"url": "https://test"}}
        result = migrate(data)
        assert result["version"] == 2
        assert "subscription_page" not in result

    def test_data_preserved_through_migration(self) -> None:
        data = {
            "version": 1,
            "panel": {"url": "https://test"},
            "nodes": [{"ip": "198.51.100.1"}],
            "custom_field": "preserved",
        }
        result = migrate(data)
        assert result["version"] == 2
        assert result["nodes"] == [{"ip": "198.51.100.1"}]
        assert result["custom_field"] == "preserved"
