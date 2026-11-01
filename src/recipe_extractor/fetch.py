# SPDX-License-Identifier: Apache-2.0
"""SSRF-safe HTTP fetcher with manual redirect verification."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlparse

import requests

from recipe_extractor import __version__

DEFAULT_USER_AGENT = (
    f"RecipeExtractor/{__version__} (+https://github.com/rnc/recipe-extractor)"
)
DEFAULT_MAX_PAGE_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_REDIRECTS = 5

CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")


class FetchError(Exception):
    """Raised when fetching a remote resource fails or is blocked."""


def is_ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether an IP address is a safe public address."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_ip_allowed(ip.ipv4_mapped)

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    return not (isinstance(ip, ipaddress.IPv4Address) and ip in CARRIER_GRADE_NAT)


def validate_url_safety(url: str) -> None:
    """Validate URL scheme and ensure hostname does not resolve to private IPs."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise FetchError(f"Unsupported URL scheme: '{parsed.scheme}'")

    hostname = parsed.hostname
    if not hostname:
        raise FetchError("URL contains no hostname")

    # Check if hostname is directly an IP literal
    try:
        direct_ip = ipaddress.ip_address(hostname)
        if not is_ip_allowed(direct_ip):
            raise FetchError(f"Access to IP address {direct_ip} is forbidden")
        return
    except ValueError:
        pass

    # Resolve hostname via DNS
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise FetchError(f"Failed to resolve host '{hostname}': {e}") from e

    if not addr_info:
        raise FetchError(f"No IP addresses found for host '{hostname}'")

    for entry in addr_info:
        ip_str = entry[4][0]
        ip = ipaddress.ip_address(ip_str)
        if not is_ip_allowed(ip):
            raise FetchError(
                f"Host '{hostname}' resolved to blocked IP address {ip_str}"
            )


@dataclass
class FetchedResource:
    """Representation of a safely fetched HTTP resource."""

    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        """Decode content using charset from headers or fallback to utf-8."""
        content_type = self.headers.get("content-type", "")
        encoding = "utf-8"
        if "charset=" in content_type:
            parts = content_type.split("charset=")
            if len(parts) > 1:
                encoding = parts[1].split(";")[0].strip().strip('"').strip("'")
        try:
            return self.content.decode(encoding, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


class Fetcher(Protocol):
    """Protocol for fetching resources (allows swapping with SnapshotFetcher)."""

    def fetch(
        self,
        url: str,
        *,
        max_size_bytes: int = DEFAULT_MAX_PAGE_BYTES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> FetchedResource: ...


class SafeFetcher:
    """SSRF-safe HTTP client enforcing DNS checks, manual redirects, and size caps."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        self.user_agent = user_agent
        self.max_redirects = max_redirects
        self.session = requests.Session()

    def fetch(
        self,
        url: str,
        *,
        max_size_bytes: int = DEFAULT_MAX_PAGE_BYTES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> FetchedResource:
        """Fetch a URL safely, validating every redirect hop."""
        current_url = url
        redirect_count = 0

        while True:
            validate_url_safety(current_url)

            headers = {
                "User-Agent": self.user_agent,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/*,*/*;q=0.8"
                ),
                "Accept-Language": "en-GB,en;q=0.9",
            }

            try:
                response = self.session.get(
                    current_url,
                    headers=headers,
                    timeout=timeout,
                    stream=True,
                    allow_redirects=False,
                )
            except requests.RequestException as e:
                raise FetchError(f"Request failed for {current_url}: {e}") from e

            # Handle redirects manually
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > self.max_redirects:
                    response.close()
                    raise FetchError(
                        f"Exceeded maximum redirect limit ({self.max_redirects})"
                    )

                location = response.headers.get("Location")
                if not location:
                    response.close()
                    raise FetchError("Redirect response missing Location header")

                current_url = urljoin(current_url, location)
                response.close()
                continue

            # Read content with size limit
            chunks: list[bytes] = []
            total_bytes = 0

            try:
                for chunk in response.iter_content(chunk_size=8192):
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        response.close()
                        raise FetchError(
                            f"Response size exceeded limit of {max_size_bytes} bytes"
                        )
                    chunks.append(chunk)
            finally:
                response.close()

            if response.status_code >= 400:
                raise FetchError(
                    f"HTTP error {response.status_code} while fetching {current_url}"
                )

            return FetchedResource(
                url=current_url,
                status_code=response.status_code,
                headers=dict(response.headers),
                content=b"".join(chunks),
            )
