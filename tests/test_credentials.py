"""Tests for credential dataclass and YAML persistence."""

from __future__ import annotations

from pathlib import Path

from meridian.credentials import ServerCredentials, creds_path


class TestServerCredentials:
    def test_load_missing_file(self, tmp_path: Path) -> None:
        creds = ServerCredentials.load(tmp_path / "nonexistent.yml")
        assert creds.panel_username == ""
        assert creds.has_credentials is False

    def test_load_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yml"
        f.write_text("")
        creds = ServerCredentials.load(f)
        assert creds.panel_username == ""

    def test_load_sample(self, sample_proxy_yml: Path) -> None:
        creds = ServerCredentials.load(sample_proxy_yml)
        assert creds.panel_username == "admin"
        assert creds.panel_password == "s3cret!pass"
        assert creds.panel_web_base_path == "abc123"
        assert creds.reality_sni == "www.microsoft.com"
        assert creds.reality_uuid == "550e8400-e29b-41d4-a716-446655440000"
        assert creds.scanned_sni == "dl.google.com"
        assert creds.xhttp_enabled is False
        assert creds.domain == ""
        assert creds.has_credentials is True
        assert creds.has_domain is False

    def test_load_with_domain(self, tmp_path: Path) -> None:
        f = tmp_path / "proxy.yml"
        f.write_text("panel_username: admin\npanel_password: pass\ndomain: example.com\n")
        creds = ServerCredentials.load(f)
        assert creds.has_domain is True
        assert creds.domain == "example.com"

    def test_load_ignores_unknown_fields(self, tmp_path: Path) -> None:
        f = tmp_path / "proxy.yml"
        f.write_text("panel_username: admin\nfuture_field: value\nanother: 42\n")
        creds = ServerCredentials.load(f)
        assert creds.panel_username == "admin"
        # Should not raise — unknown fields are silently ignored

    def test_save_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "subdir" / "proxy.yml"
        creds = ServerCredentials(panel_username="admin", panel_password="pass")
        creds.save(path)
        assert path.exists()
        assert oct(path.stat().st_mode)[-3:] == "600"

        loaded = ServerCredentials.load(path)
        assert loaded.panel_username == "admin"
        assert loaded.panel_password == "pass"

    def test_save_preserves_unknown_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "proxy.yml"
        path.write_text("panel_username: old\nfuture_field: keep_me\n")
        path.chmod(0o600)

        creds = ServerCredentials(panel_username="new", panel_password="pass")
        creds.save(path)

        # Re-read raw YAML to check unknown field preserved
        import yaml

        data = yaml.safe_load(path.read_text())
        assert data["panel_username"] == "new"
        assert data["future_field"] == "keep_me"

    def test_save_handles_booleans(self, tmp_path: Path) -> None:
        path = tmp_path / "proxy.yml"
        creds = ServerCredentials(xhttp_enabled=False)
        creds.save(path)

        import yaml

        data = yaml.safe_load(path.read_text())
        assert data["xhttp_enabled"] is False

    def test_load_handles_none_values(self, tmp_path: Path) -> None:
        f = tmp_path / "proxy.yml"
        f.write_text("panel_username: admin\nreality_sni:\n")
        creds = ServerCredentials.load(f)
        assert creds.panel_username == "admin"
        assert creds.reality_sni == ""  # None filtered out, default used

    def test_load_special_chars_in_password(self, tmp_path: Path) -> None:
        """This is the case that broke the bash grep/awk approach."""
        f = tmp_path / "proxy.yml"
        f.write_text('panel_username: admin\npanel_password: "p@ss: with spaces & special!"\n')
        creds = ServerCredentials.load(f)
        assert creds.panel_password == "p@ss: with spaces & special!"


class TestCredsPath:
    def test_creds_path(self, tmp_path: Path) -> None:
        result = creds_path(tmp_path, "1.2.3.4")
        assert result == tmp_path / "1.2.3.4" / "proxy.yml"
