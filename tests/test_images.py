# SPDX-License-Identifier: Apache-2.0
"""Tests for image discovery, format sniffing, and embedding."""

from pathlib import Path

from recipe_extractor.fetch import FetchedResource
from recipe_extractor.images import (
    discover_image_urls,
    fetch_and_embed_images,
    is_ad_or_clutter_url,
    sniff_image_mime,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

DUMMY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
DUMMY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
DUMMY_GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
DUMMY_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x000\x01\x00\x9d\x01*"
DUMMY_AVIF = b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00mif1avif\x00\x00\x00\x00"
DUMMY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def test_sniff_image_mime_recognises_valid_types() -> None:
    assert sniff_image_mime(DUMMY_JPEG) == "image/jpeg"
    assert sniff_image_mime(DUMMY_PNG) == "image/png"
    assert sniff_image_mime(DUMMY_GIF) == "image/gif"
    assert sniff_image_mime(DUMMY_WEBP) == "image/webp"
    assert sniff_image_mime(DUMMY_AVIF) == "image/avif"


def test_sniff_image_mime_rejects_svg_and_invalid_bytes() -> None:
    assert sniff_image_mime(DUMMY_SVG) is None
    assert sniff_image_mime(b"<!DOCTYPE html><html>") is None
    assert sniff_image_mime(b"random corrupt string") is None
    assert sniff_image_mime(b"") is None


def test_discover_image_urls_from_jsonld_and_opengraph() -> None:
    html = (FIXTURES_DIR / "simple_recipe.html").read_text()
    urls = discover_image_urls(html, base_url="https://example.com/recipe")
    assert "https://example.com/images/lemon-cake-1.jpg" in urls
    assert "https://example.com/images/lemon-cake-2.png" in urls
    assert "https://example.com/images/lemon-cake-og.jpg" in urls


class MockFetcher:
    """Mock fetcher providing dummy image bytes for testing."""

    def fetch(
        self,
        url: str,
        *,
        max_size_bytes: int = 10 * 1024 * 1024,
        timeout: float = 10.0,
    ) -> FetchedResource:
        if url.endswith(".png"):
            content = DUMMY_PNG
            content_type = "image/png"
        elif url.endswith(".webp"):
            content = DUMMY_WEBP
            content_type = "image/webp"
        elif url.endswith(".svg"):
            content = DUMMY_SVG
            content_type = "image/svg+xml"
        else:
            content = DUMMY_JPEG
            content_type = "image/jpeg"

        return FetchedResource(
            url=url,
            status_code=200,
            headers={"content-type": content_type},
            content=content,
        )


def test_fetch_and_embed_images_embeds_and_filters_svg() -> None:
    fetcher = MockFetcher()
    candidate_urls = [
        "https://example.com/valid.jpg",
        "https://example.com/unsafe.svg",
        "https://example.com/photo.png",
    ]

    images, warnings = fetch_and_embed_images(candidate_urls, fetcher)
    assert len(images) == 2
    assert images[0].src.startswith("data:image/jpeg;base64,")
    assert images[0].selected is True
    assert images[1].src.startswith("data:image/png;base64,")
    assert images[1].selected is False
    assert any("unsupported or unsafe" in w for w in warnings)


def test_is_ad_or_clutter_url() -> None:
    blocklist = {"adservice.google.com", "doubleclick.net"}
    assert is_ad_or_clutter_url("https://doubleclick.net/ad.jpg", blocklist) is True
    assert (
        is_ad_or_clutter_url("https://sub.adservice.google.com/pixel.png", blocklist)
        is True
    )
    assert is_ad_or_clutter_url("https://example.com/tracking/pixel.gif") is True
    assert is_ad_or_clutter_url("https://secure.gravatar.com/avatar/123") is True
    assert (
        is_ad_or_clutter_url("https://example.com/photos/delicious-cake.jpg") is False
    )


def test_fallback_image_discovery_filters_clutter_containers() -> None:
    html = """
    <html>
      <body>
        <aside class="sidebar-ad">
          <img src="https://example.com/sidebar-banner.jpg" />
        </aside>
        <div class="advertisement">
          <img src="https://example.com/ad-box.jpg" />
        </div>
        <div class="recipe-content">
          <img src="https://example.com/real-recipe-photo.jpg" />
        </div>
      </body>
    </html>
    """
    urls = discover_image_urls(html, base_url="https://example.com")
    assert "https://example.com/real-recipe-photo.jpg" in urls
    assert "https://example.com/sidebar-banner.jpg" not in urls
    assert "https://example.com/ad-box.jpg" not in urls
