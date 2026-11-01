#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Download sample pages and their immediate images into tests/samples_private/.

Usage:
    python scripts/snapshot_samples.py [--refresh] [slug]
    python scripts/snapshot_samples.py --add <url> [--slug <slug>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from recipe_extractor.extract import extract_recipe
from recipe_extractor.fetch import SafeFetcher
from recipe_extractor.images import discover_image_urls, sniff_image_mime

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "tests" / "samples" / "manifest.toml"
DEFAULT_SAMPLES_DIR = ROOT / "tests" / "samples_private"

ALLOWED_HEADERS = {"content-type", "last-modified", "etag", "date"}


def get_samples_dir() -> Path:
    env_dir = os.environ.get("RECIPE_SAMPLES_DIR")
    if env_dir:
        return Path(env_dir)
    return DEFAULT_SAMPLES_DIR


def snapshot_sample(
    slug: str,
    url: str,
    output_dir: Path,
    *,
    refresh: bool = False,
) -> None:
    sample_dir = output_dir / slug
    if sample_dir.exists() and not refresh:
        print(
            f"[{slug}] Snapshot already exists at {sample_dir}, skipping "
            "(use --refresh to update)"
        )
        return

    sample_dir.mkdir(parents=True, exist_ok=True)
    images_dir = sample_dir / "images"
    images_dir.mkdir(exist_ok=True)

    print(f"[{slug}] Fetching {url}...")
    fetcher = SafeFetcher()
    page = fetcher.fetch(url)

    # Write page.html
    (sample_dir / "page.html").write_text(page.text, encoding="utf-8")

    # Filter safe headers
    filtered_headers = {
        k: v for k, v in page.headers.items() if k.lower() in ALLOWED_HEADERS
    }

    meta = {
        "slug": slug,
        "requested_url": url,
        "final_url": page.url,
        "status_code": page.status_code,
        "fetch_date": datetime.now(UTC).isoformat(),
        "headers": filtered_headers,
    }
    (sample_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Discover and download immediate images
    candidate_urls = discover_image_urls(page.text, base_url=page.url)
    images_map: list[dict[str, str]] = []

    for idx, img_url in enumerate(candidate_urls[:5]):
        try:
            img_res = fetcher.fetch(img_url)
            mime = sniff_image_mime(img_res.content)
            if not mime:
                continue

            ext = mime.split("/")[-1].replace("jpeg", "jpg")
            filename = f"image_{idx + 1}.{ext}"
            (images_dir / filename).write_bytes(img_res.content)

            images_map.append(
                {
                    "original_url": img_url,
                    "filename": filename,
                    "mime_type": mime,
                }
            )
            print(f"  Downloaded {img_url} -> {filename}")
        except Exception as e:
            print(f"  Failed to download image {img_url}: {e}", file=sys.stderr)

    (sample_dir / "images.json").write_text(
        json.dumps(images_map, indent=2), encoding="utf-8"
    )
    print(f"[{slug}] Saved successfully to {sample_dir}\n")


def slugify_url(url: str) -> str:
    """Generate a clean identifier slug from a URL path."""
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    for part in reversed(path_parts):
        clean = re.sub(r"[^\w-]", "", part).replace("-", "_").strip("_").lower()
        if len(clean) > 3 and not (
            clean.isalnum() and len(clean) < 10 and any(c.isdigit() for c in clean)
        ):
            return clean
    if path_parts:
        return (
            re.sub(r"[^\w-]", "", path_parts[-1]).replace("-", "_").strip("_").lower()
        )
    return "sample_recipe"


def add_sample_from_url(
    url: str,
    output_dir: Path,
    *,
    custom_slug: str | None = None,
    refresh: bool = False,
) -> None:
    """Fetch recipe, snapshot it into private samples, and record into manifest.toml."""
    slug = custom_slug or slugify_url(url)
    print(f"Adding sample '{slug}' from {url}...")

    # Fetch page
    fetcher = SafeFetcher()
    page = fetcher.fetch(url)

    # Extract recipe to determine expectations
    recipe, _ = extract_recipe(page.text, url=page.url, download_images=False)
    title = recipe.title or "Untitled Recipe"
    min_ingredients = max(1, len(recipe.ingredients))
    min_steps = max(1, len(recipe.steps))

    # Snapshot to private dir
    snapshot_sample(slug, url, output_dir, refresh=True)

    # Read existing manifest
    manifest_data: dict[str, Any] = {"samples": {}}
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "rb") as f:
                manifest_data = tomllib.load(f)
        except Exception as e:
            print(f"Warning: could not parse existing manifest: {e}", file=sys.stderr)

    if "samples" not in manifest_data:
        manifest_data["samples"] = {}

    manifest_data["samples"][slug] = {
        "url": url,
        "title": title,
        "min_ingredients": min_ingredients,
        "min_steps": min_steps,
    }

    # Format manifest.toml
    lines = [
        "# SPDX-License-Identifier: Apache-2.0",
        "# Manifest of sample recipe URLs and test expectations.",
        "# Real snapshots are downloaded into tests/samples_private/ (gitignored).",
        "",
        "[samples]",
    ]
    for s_name, s_info in manifest_data["samples"].items():
        lines.append(f"\n[samples.{s_name}]")
        lines.append(f'url = "{s_info["url"]}"')
        lines.append(f'title = "{s_info["title"]}"')
        lines.append(f'min_ingredients = {s_info["min_ingredients"]}')
        lines.append(f'min_steps = {s_info["min_steps"]}')

    lines.append("")
    MANIFEST_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Updated {MANIFEST_PATH} with sample '{slug}'")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download sample recipe snapshots into tests/samples_private/"
    )
    parser.add_argument(
        "--add",
        metavar="URL",
        help="Add a new sample recipe URL to manifest and snapshot",
    )
    parser.add_argument("--slug", help="Custom slug when adding a sample with --add")
    parser.add_argument(
        "--refresh", action="store_true", help="Overwrite existing snapshots"
    )
    parser.add_argument(
        "slug_arg",
        nargs="?",
        metavar="slug",
        help="Optional specific slug from manifest to snapshot",
    )
    args = parser.parse_args()

    output_dir = get_samples_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.add:
        add_sample_from_url(
            args.add,
            output_dir,
            custom_slug=args.slug,
            refresh=args.refresh,
        )
        return

    if not MANIFEST_PATH.exists():
        print(f"Manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(MANIFEST_PATH, "rb") as f:
        data = tomllib.load(f)

    samples = data.get("samples", {})
    if not samples:
        print("No samples configured in tests/samples/manifest.toml yet.")
        return

    target_slug = args.slug or args.slug_arg
    if target_slug:
        if target_slug not in samples:
            print(f"Slug '{target_slug}' not found in manifest.", file=sys.stderr)
            sys.exit(1)
        snapshot_sample(
            target_slug,
            samples[target_slug]["url"],
            output_dir,
            refresh=args.refresh,
        )
    else:
        for slug, info in samples.items():
            snapshot_sample(slug, info["url"], output_dir, refresh=args.refresh)


if __name__ == "__main__":
    main()
