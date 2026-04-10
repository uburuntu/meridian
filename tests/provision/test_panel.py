"""Tests for panel provisioning helpers."""

from __future__ import annotations

import pytest

from meridian.panel import PanelError
from meridian.provision.panel import _parse_vlessenc_output


class TestParseVlessEncOutput:
    def test_prefers_mlkem_section_from_new_xray_output(self) -> None:
        output = """
Choose one Authentication to use, do not mix them. Ephemeral key exchange is Post-Quantum safe anyway.

Authentication: X25519, not Post-Quantum
"decryption": "mlkem768x25519plus.native.600s.x25519-server"
"encryption": "mlkem768x25519plus.native.0rtt.x25519-client"

Authentication: ML-KEM-768, Post-Quantum
"decryption": "mlkem768x25519plus.native.600s.mlkem-server"
"encryption": "mlkem768x25519plus.native.0rtt.mlkem-client"
"""
        private_key, public_key = _parse_vlessenc_output(output)
        assert private_key == "mlkem768x25519plus.native.600s.mlkem-server"
        assert public_key == "mlkem768x25519plus.native.0rtt.mlkem-client"

    def test_supports_legacy_single_pair_output(self) -> None:
        output = """
PrivateKey: legacy-private
Encryption: legacy-public
"""
        private_key, public_key = _parse_vlessenc_output(output)
        assert private_key == "legacy-private"
        assert public_key == "legacy-public"

    def test_raises_when_output_is_unrecognized(self) -> None:
        with pytest.raises(PanelError):
            _parse_vlessenc_output("unexpected output")
