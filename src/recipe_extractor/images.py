# SPDX-License-Identifier: Apache-2.0
"""Image discovery, validation, download, and data-URI embedding."""

from __future__ import annotations

import base64
import json
import logging
import tempfile
import time
from pathlib import Path
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

PETER_LOWE_LIST_URL = (
    "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=nohtml&showintro=0"
)
CACHE_MAX_AGE_SECONDS = 86400  # 24 hours
TEMP_CACHE_FILE = Path(tempfile.gettempdir()) / "recipe_extractor_ad_servers.txt"

# In-memory runtime cache for the Peter Lowe ad server list
_AD_SERVER_CACHE: set[str] | None = None

CLUTTER_URL_SUBSTRINGS = (
    "/ads/",
    "/advert/",
    "/banner/",
    "pixel",
    "1x1",
    "tracking",
    "gravatar.com/avatar",
    "author-avatar",
    "badge",
    "icon-",
    "/icons/",
    "social-share",
)

CLUTTER_CONTAINER_CLASSES = (
    "ad",
    "advert",
    "advertisement",
    "sponsor",
    "sponsored",
    "sidebar",
    "social",
    "share",
    "author",
    "profile",
    "comments",
    "footer",
    "header",
)


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


def get_ad_server_blocklist(fetcher: Fetcher | None = None) -> set[str]:
    """Retrieve Peter Lowe's ad server list from disk cache or fetch on-demand."""
    global _AD_SERVER_CACHE
    if _AD_SERVER_CACHE is not None:
        return _AD_SERVER_CACHE

    domains: set[str] = set()
    text = ""

    # 1. Check if temporary cache file exists and is still fresh (< 24h old)
    if TEMP_CACHE_FILE.exists():
        try:
            mtime = TEMP_CACHE_FILE.stat().st_mtime
            if time.time() - mtime < CACHE_MAX_AGE_SECONDS:
                text = TEMP_CACHE_FILE.read_text(encoding="utf-8")
        except Exception as e:
            logger.debug("Could not read temp ad cache file: %s", e)

    # 2. Fetch fresh list over the network if not in temp cache
    if not text:
        try:
            if fetcher is not None:
                res = fetcher.fetch(PETER_LOWE_LIST_URL, timeout=5.0)
                text = res.text
            else:
                import requests

                resp = requests.get(PETER_LOWE_LIST_URL, timeout=5.0)
                text = resp.text if resp.status_code == 200 else ""

            if text:
                try:
                    TEMP_CACHE_FILE.write_text(text, encoding="utf-8")
                except Exception as e:
                    logger.debug("Could not save ad cache to temp file: %s", e)
        except Exception as e:
            logger.debug(
                "Could not fetch Peter Lowe list (offline or network error): %s", e
            )

    # 3. Parse domain list into in-memory set
    if text:
        for line in text.splitlines():
            item = line.strip().lower()
            if item and not item.startswith("#"):
                domains.add(item)
        logger.info(
            "Loaded %d ad server domains (from temp cache/remote)", len(domains)
        )

    _AD_SERVER_CACHE = domains
    return _AD_SERVER_CACHE


def is_ad_or_clutter_url(url: str, blocklist: set[str] | None = None) -> bool:
    """Check if an image URL matches ad servers or clutter patterns."""
    url_lower = url.lower()
    if any(sub in url_lower for sub in CLUTTER_URL_SUBSTRINGS):
        return True

    if blocklist:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname in blocklist:
            return True
        # Check parent domains
        parts = hostname.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[1:])
            if parent in blocklist:
                return True

    return False


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


def discover_image_urls(
    html: str,
    base_url: str = "",
    *,
    fetcher: Fetcher | None = None,
) -> list[str]:
    """Find image URLs from JSON-LD, OpenGraph, and fallback HTML tags."""
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

    # 3. Fallback: If no structured images found, scrape non-clutter <img> tags
    if not found_urls:
        ad_blocklist = get_ad_server_blocklist(fetcher)
        for img in soup.find_all("img"):
            # Check if inside aside, nav, footer, header
            if img.find_parent(["aside", "nav", "footer", "header"]):
                continue

            # Check parent class/id for ad or clutter hints
            parent_clutter = False
            for parent in img.parents:
                raw_cls = parent.get("class")
                classes = (
                    " ".join(raw_cls)
                    if isinstance(raw_cls, list)
                    else str(raw_cls or "")
                ).lower()
                pid = str(parent.get("id") or "").lower()
                if any(c in classes or c in pid for c in CLUTTER_CONTAINER_CLASSES):
                    parent_clutter = True
                    break
            if parent_clutter:
                continue

            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if isinstance(src, str) and src.strip():
                resolved_src = (
                    urljoin(base_url, src.strip()) if base_url else src.strip()
                )
                if not is_ad_or_clutter_url(resolved_src, ad_blocklist):
                    found_urls.append(src.strip())
    else:
        ad_blocklist = None

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
            if not is_ad_or_clutter_url(resolved, ad_blocklist):
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
