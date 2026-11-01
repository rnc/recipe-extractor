# SPDX-License-Identifier: Apache-2.0
"""Image discovery, validation, download, and data-URI embedding."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from recipe_extractor.fetch import DEFAULT_MAX_IMAGE_BYTES, Fetcher, FetchError
from recipe_extractor.models import RecipeImage

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/avif",
}


def sniff_image_mime(content: bytes) -> str | None:
    """Sniff real MIME type from magic bytes. Returns None if invalid or disallowed."""
    if len(content) < 4:
        return None

    # JPEG: starts with FF D8 FF
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # PNG: starts with 89 50 4E 47 0D 0A 1A 0A
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # GIF: GIF87a or GIF89a
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"

    # WebP: RIFF....WEBP
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"

    # AVIF: ....ftypavif or ....ftypavis
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in (b"avif", b"avis", b"mif1"):
            return "image/avif"

    return None


def _extract_urls_from_ld_json_value(value: Any) -> list[str]:
    """Extract image URLs recursively from JSON-LD property values."""
    urls: list[str] = []
    if isinstance(value, str):
        if value.strip():
            urls.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            urls.extend(_extract_urls_from_ld_json_value(item))
    elif isinstance(value, dict):
        if "url" in value and isinstance(value["url"], str):
            urls.append(value["url"].strip())
        elif "contentUrl" in value and isinstance(value["contentUrl"], str):
            urls.append(value["contentUrl"].strip())
    return urls


def discover_image_urls(html: str, base_url: str = "") -> list[str]:
    """Find all candidate recipe image URLs from JSON-LD and OpenGraph tags."""
    found_urls: list[str] = []
    soup = BeautifulSoup(html, "html.parser")

    # 1. Search JSON-LD scripts for Recipe images
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except Exception as e:
            logger.debug("Skipping unparseable JSON-LD: %s", e)
            continue

        items = data if isinstance(data, list) else [data]
        # Handle @graph wrapper
        expanded_items: list[dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict):
                if "@graph" in it and isinstance(it["@graph"], list):
                    expanded_items.extend(
                        g for g in it["@graph"] if isinstance(g, dict)
                    )
                else:
                    expanded_items.append(it)

        for item in expanded_items:
            type_val = item.get("@type", "")
            is_recipe = (
                type_val == "Recipe"
                or (isinstance(type_val, list) and "Recipe" in type_val)
                or (isinstance(type_val, str) and type_val.endswith("Recipe"))
            )
            if is_recipe and "image" in item:
                found_urls.extend(_extract_urls_from_ld_json_value(item["image"]))

    # 2. OpenGraph and Twitter image meta tags
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        if isinstance(prop, str) and prop.lower() in (
            "og:image",
            "og:image:url",
            "twitter:image",
        ):
            content = meta.get("content", "")
            if isinstance(content, str) and content.strip():
                found_urls.append(content.strip())

    # Normalise and deduplicate URLs
    clean_urls: list[str] = []
    seen: set[str] = set()

    for u in found_urls:
        resolved = urljoin(base_url, u) if base_url else u

        parsed = urlparse(resolved)
        if parsed.scheme.lower() not in ("http", "https"):
            continue

        if resolved not in seen:
            seen.add(resolved)
            clean_urls.append(resolved)

    return clean_urls


def fetch_and_embed_images(
    image_urls: list[str],
    fetcher: Fetcher,
    *,
    max_images: int = 5,
    max_size_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> tuple[list[RecipeImage], list[str]]:
    """Download candidate images, validate formats, and convert to data: URIs."""
    images: list[RecipeImage] = []
    warnings: list[str] = []

    for url in image_urls[:max_images]:
        try:
            resource = fetcher.fetch(url, max_size_bytes=max_size_bytes)
        except FetchError as e:
            msg = f"Failed to download image from {url}: {e}"
            logger.warning(msg)
            warnings.append(msg)
            continue

        mime = sniff_image_mime(resource.content)
        if not mime or mime not in ALLOWED_IMAGE_MIMES:
            msg = (
                f"Skipping image from {url}: unsupported or unsafe format "
                f"(detected: {mime})"
            )
            logger.warning(msg)
            warnings.append(msg)
            continue

        encoded = base64.b64encode(resource.content).decode("ascii")
        data_uri = f"data:{mime};base64,{encoded}"

        images.append(
            RecipeImage(
                src=data_uri,
                alt=f"Recipe photo {len(images) + 1}",
                selected=(len(images) == 0),  # First valid image is selected by default
                original_url=url,
            )
        )

    return images, warnings
