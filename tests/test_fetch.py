# SPDX-License-Identifier: Apache-2.0
"""Tests for SSRF-safe HTTP fetching."""

import ipaddress

import pytest

from recipe_extractor.fetch import (
    FetchError,
    is_ip_allowed,
    validate_url_safety,
)


def test_ip_allowlist_blocks_private_and_loopback() -> None:
    blocked_ips = [
        "127.0.0.1",
        "127.0.1.1",
        "10.0.0.1",
        "10.254.254.254",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # AWS/GCP/Azure metadata
        "100.64.0.1",  # Carrier-grade NAT
        "0.0.0.0",  # noqa: S104
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",  # IPv4-mapped private
    ]
    for ip_str in blocked_ips:
        ip = ipaddress.ip_address(ip_str)
        assert not is_ip_allowed(ip), f"Expected {ip_str} to be blocked"


def test_ip_allowlist_allows_public_ips() -> None:
    public_ips = [
        "8.8.8.8",
        "1.1.1.1",
        "151.101.1.140",
        "2606:4700:4700::1111",
    ]
    for ip_str in public_ips:
        ip = ipaddress.ip_address(ip_str)
        assert is_ip_allowed(ip), f"Expected {ip_str} to be allowed"


def test_validate_url_safety_rejects_bad_schemes() -> None:
    bad_urls = [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com",
        "javascript:alert(1)",
        "data:text/html,<h1>hi</h1>",
    ]
    for url in bad_urls:
        with pytest.raises(FetchError, match="Unsupported URL scheme"):
            validate_url_safety(url)


def test_validate_url_safety_rejects_direct_private_ips() -> None:
    with pytest.raises(FetchError, match="forbidden"):
        validate_url_safety("http://127.0.0.1:8000/api")

    with pytest.raises(FetchError, match="forbidden"):
        validate_url_safety("http://169.254.169.254/latest/meta-data")


def test_validate_url_safety_rejects_empty_or_invalid_host() -> None:
    with pytest.raises(FetchError):
        validate_url_safety("http://")
