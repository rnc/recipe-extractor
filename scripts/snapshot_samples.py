#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Download sample pages and their immediate images into tests/samples_private/.

Usage:
    python scripts/snapshot_samples.py [--refresh] [slug]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download sample recipe snapshots into tests/samples_private/"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Overwrite existing snapshots"
    )
    parser.add_argument(
        "slug", nargs="?", help="Optional specific slug from manifest to snapshot"
    )
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"Manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(MANIFEST_PATH, "rb") as f:
        data = tomllib.load(f)

    samples = data.get("samples", {})
    if not samples:
        print("No samples configured in tests/samples/manifest.toml yet.")
        return

    output_dir = get_samples_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.slug:
        if args.slug not in samples:
            print(f"Slug '{args.slug}' not found in manifest.", file=sys.stderr)
            sys.exit(1)
        snapshot_sample(
            args.slug,
            samples[args.slug]["url"],
            output_dir,
            refresh=args.refresh,
        )
    else:
        for slug, info in samples.items():
            snapshot_sample(slug, info["url"], output_dir, refresh=args.refresh)


if __name__ == "__main__":
    main()
