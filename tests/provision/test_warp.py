"""Tests for Cloudflare WARP provisioning steps."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from meridian.provision.steps import ProvisionContext
from meridian.provision.warp import WARP_PROXY_PORT, ConfigureWarpOutbound, InstallWarp
from tests.provision.conftest import MockConnection


class _WarpMockConnection(MockConnection):
    """MockConnection that tracks warp-cli connect state.

    Returns Disconnected on first status check, Connected after connect.
    """

    def __init__(self) -> None:
        super().__init__()
        self._connected = False

    def run(self, command: str, timeout: int = 30, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "status" in command and "warp-cli" in command:
            self._calls.append(command)
            if self._connected:
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="Status: Connected", stderr="")
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="Status: Disconnected", stderr="")
        if "connect" in command and "warp-cli" in command and "disconnect" not in command:
            self._connected = True
        return super().run(command, timeout, **kwargs)


# ---------------------------------------------------------------------------
# InstallWarp
# ---------------------------------------------------------------------------


class TestInstallWarp:
    def test_already_connected_returns_ok(self, tmp_path: Path):
        conn = MockConnection()
        # Pattern must match "warp-cli --accept-tos status 2>/dev/null"
        conn.when("accept-tos status", stdout="Status: Connected")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        result = InstallWarp().run(conn, ctx)
        assert result.status == "ok"
        assert "already connected" in result.detail

    def test_fresh_install_returns_changed(self, tmp_path: Path):
        conn = _WarpMockConnection()
        conn.when("command -v warp-cli", rc=1)
        conn.when("curl -fsSL", stdout="")
        conn.when("tee", stdout="")
        conn.when("apt-get update", stdout="")
        conn.when("systemctl enable", stdout="")
        conn.when("registration new", stdout="Success")
        conn.when("mode proxy", stdout="")
        conn.when("proxy port", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        result = InstallWarp().run(conn, ctx)
        assert result.status == "changed"
        assert str(WARP_PROXY_PORT) in result.detail

    def test_already_installed_but_disconnected(self, tmp_path: Path):
        """warp-cli exists but not connected — register and connect."""
        conn = _WarpMockConnection()
        conn.when("command -v warp-cli", stdout="/usr/bin/warp-cli")
        conn.when("systemctl enable", stdout="")
        conn.when("registration new", stdout="Success")
        conn.when("mode proxy", stdout="")
        conn.when("proxy port", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        result = InstallWarp().run(conn, ctx)
        assert result.status == "changed"
        # Should NOT try to install the package
        conn.assert_not_called_with_pattern("apt-get install")

    def test_gpg_key_failure_returns_failed(self, tmp_path: Path):
        conn = _WarpMockConnection()
        conn.when("command -v warp-cli", rc=1)
        conn.when("curl -fsSL", rc=1)

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        result = InstallWarp().run(conn, ctx)
        assert result.status == "failed"
        assert "GPG" in result.detail

    def test_sets_proxy_mode(self, tmp_path: Path):
        """Must use proxy mode (SOCKS5), not full tunnel (would break SSH)."""
        conn = _WarpMockConnection()
        conn.when("command -v warp-cli", stdout="/usr/bin/warp-cli")
        conn.when("systemctl enable", stdout="")
        conn.when("registration new", stdout="Success")
        conn.when("mode proxy", stdout="")
        conn.when("proxy port", stdout="")

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        InstallWarp().run(conn, ctx)
        conn.assert_called_with_pattern("mode proxy")


# ---------------------------------------------------------------------------
# ConfigureWarpOutbound
# ---------------------------------------------------------------------------


class _MockPanel:
    """Minimal panel mock for Xray config fetch/update."""

    def __init__(self, xray_config: dict | None = None):
        self._config = xray_config or {
            "outbounds": [{"protocol": "freedom", "tag": "direct"}],
            "routing": {"rules": []},
        }
        self._updated: str | None = None
        self._restarted = False

    def api_post_empty(self, path: str) -> dict:
        if path == "/panel/xray/":
            wrapper = {"xraySetting": json.dumps(self._config)}
            return {"success": True, "obj": json.dumps(wrapper)}
        if path == "/panel/api/server/restartXrayService":
            self._restarted = True
            return {"success": True}
        return {"success": True}

    def api_post_form(self, path: str, form_data: str) -> dict:
        self._updated = form_data
        return {"success": True}

    @property
    def updated_config(self) -> dict | None:
        if self._updated is None:
            return None
        from urllib.parse import unquote

        raw = self._updated.replace("xraySetting=", "")
        return json.loads(unquote(raw))


class TestConfigureWarpOutbound:
    def test_already_configured_returns_ok(self, tmp_path: Path):
        panel = _MockPanel(
            {
                "outbounds": [
                    {"protocol": "socks", "tag": "warp", "settings": {}},
                    {"protocol": "freedom", "tag": "direct"},
                ],
            }
        )
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        ctx["panel"] = panel

        result = ConfigureWarpOutbound().run(MockConnection(), ctx)
        assert result.status == "ok"
        assert "already configured" in result.detail

    def test_adds_warp_as_first_outbound(self, tmp_path: Path):
        panel = _MockPanel(
            {
                "outbounds": [{"protocol": "freedom", "tag": "direct"}],
                "routing": {"rules": []},
            }
        )
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        ctx["panel"] = panel

        result = ConfigureWarpOutbound().run(MockConnection(), ctx)
        assert result.status == "changed"

        updated = panel.updated_config
        assert updated is not None
        outbounds = updated["outbounds"]
        # WARP must be FIRST (Xray uses first outbound as default)
        assert outbounds[0]["tag"] == "warp"
        assert outbounds[0]["protocol"] == "socks"
        # Direct still present as fallback
        assert any(o["tag"] == "direct" for o in outbounds)

    def test_warp_points_to_correct_port(self, tmp_path: Path):
        panel = _MockPanel()
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        ctx["panel"] = panel

        ConfigureWarpOutbound().run(MockConnection(), ctx)

        updated = panel.updated_config
        assert updated is not None
        warp_outbound = updated["outbounds"][0]
        server = warp_outbound["settings"]["servers"][0]
        assert server["address"] == "127.0.0.1"
        assert server["port"] == WARP_PROXY_PORT

    def test_preserves_existing_outbounds(self, tmp_path: Path):
        """WARP should be inserted before existing outbounds, not replace them."""
        panel = _MockPanel(
            {
                "outbounds": [
                    {"protocol": "freedom", "tag": "direct"},
                    {"protocol": "blackhole", "tag": "blocked"},
                ],
                "routing": {"rules": []},
            }
        )
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        ctx["panel"] = panel

        ConfigureWarpOutbound().run(MockConnection(), ctx)

        updated = panel.updated_config
        assert updated is not None
        tags = [o["tag"] for o in updated["outbounds"]]
        assert tags == ["warp", "direct", "blocked"]

    def test_restarts_xray(self, tmp_path: Path):
        panel = _MockPanel()
        ctx = ProvisionContext(ip="198.51.100.1", creds_dir=str(tmp_path), warp=True)
        ctx["panel"] = panel

        ConfigureWarpOutbound().run(MockConnection(), ctx)
        assert panel._restarted


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


class TestWarpPipelineIntegration:
    def test_warp_disabled_no_steps(self):
        from meridian.provision import build_setup_steps

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp/test", warp=False)
        steps = build_setup_steps(ctx)
        step_names = [s.name for s in steps]
        assert "Install Cloudflare WARP" not in step_names
        assert "Configure WARP outbound" not in step_names

    def test_warp_enabled_adds_steps(self):
        from meridian.provision import build_setup_steps

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp/test", warp=True)
        steps = build_setup_steps(ctx)
        step_names = [s.name for s in steps]
        assert "Install Cloudflare WARP" in step_names
        assert "Configure WARP outbound" in step_names

    def test_warp_steps_before_verify(self):
        """WARP steps must come before VerifyXray."""
        from meridian.provision import build_setup_steps

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp/test", warp=True)
        steps = build_setup_steps(ctx)
        step_names = [s.name for s in steps]
        warp_idx = step_names.index("Install Cloudflare WARP")
        verify_idx = step_names.index("Verify Xray configuration")
        assert warp_idx < verify_idx

    def test_warp_steps_after_geo_blocking(self):
        """WARP steps must come after ConfigureGeoBlocking."""
        from meridian.provision import build_setup_steps

        ctx = ProvisionContext(ip="198.51.100.1", creds_dir="/tmp/test", warp=True)
        steps = build_setup_steps(ctx)
        step_names = [s.name for s in steps]
        geo_idx = step_names.index("Configure geo-blocking")
        warp_idx = step_names.index("Install Cloudflare WARP")
        assert warp_idx > geo_idx
