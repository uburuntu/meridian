"""Tests for config module — IP validation and path sanitization."""

from __future__ import annotations

from meridian.config import is_ip, is_ipv4, sanitize_ip_for_path


class TestIsIpv4:
    def test_valid_ipv4(self) -> None:
        assert is_ipv4("198.51.100.1") is True

    def test_rejects_ipv6(self) -> None:
        assert is_ipv4("2001:db8::1") is False

    def test_rejects_hostname(self) -> None:
        assert is_ipv4("example.com") is False


class TestIsIp:
    def test_accepts_ipv4(self) -> None:
        assert is_ip("198.51.100.1") is True

    def test_accepts_ipv6_compressed(self) -> None:
        assert is_ip("2001:db8::1") is True

    def test_accepts_ipv6_full(self) -> None:
        assert is_ip("2001:0db8:0000:0000:0000:0000:0000:0001") is True

    def test_accepts_ipv6_loopback(self) -> None:
        assert is_ip("::1") is True

    def test_rejects_hostname(self) -> None:
        assert is_ip("example.com") is False

    def test_rejects_empty_string(self) -> None:
        assert is_ip("") is False

    def test_rejects_brackets(self) -> None:
        # Brackets are URL notation, not part of the address
        assert is_ip("[2001:db8::1]") is False

    def test_rejects_garbage(self) -> None:
        assert is_ip("not-an-ip") is False

    def test_rejects_ipv4_overflow(self) -> None:
        assert is_ip("256.1.2.3") is False


class TestSanitizeIpForPath:
    def test_ipv4_unchanged(self) -> None:
        assert sanitize_ip_for_path("198.51.100.1") == "198.51.100.1"

    def test_ipv6_colons_replaced(self) -> None:
        assert sanitize_ip_for_path("2001:db8::1") == "2001-db8--1"

    def test_ipv6_full_form(self) -> None:
        result = sanitize_ip_for_path("2001:0db8:0000:0000:0000:0000:0000:0001")
        assert result == "2001-0db8-0000-0000-0000-0000-0000-0001"

    def test_ipv6_loopback(self) -> None:
        assert sanitize_ip_for_path("::1") == "--1"
