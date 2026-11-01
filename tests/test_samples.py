# SPDX-License-Identifier: Apache-2.0
"""Live and snapshot tests for recipes defined in tests/samples/manifest.toml."""

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest

from recipe_extractor.extract import extract_recipe
from recipe_extractor.fetch import FetchedResource, FetchError, SafeFetcher

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "tests" / "samples" / "manifest.toml"
DEFAULT_SAMPLES_DIR = ROOT / "tests" / "samples_private"


def get_samples_dir() -> Path:
    env_dir = os.environ.get("RECIPE_SAMPLES_DIR")
    if env_dir:
        return Path(env_dir)
    return DEFAULT_SAMPLES_DIR


def load_manifest_samples() -> list[tuple[str, dict[str, Any]]]:
    if not MANIFEST_PATH.exists():
        return []
    with open(MANIFEST_PATH, "rb") as f:
        data = tomllib.load(f)
    samples = data.get("samples", {})
    return [(slug, info) for slug, info in samples.items()]


class SnapshotFetcher:
    """Fetcher implementation reading from a local snapshot directory."""

    def __init__(self, sample_dir: Path, requested_url: str) -> None:
        self.sample_dir = sample_dir
        self.requested_url = requested_url
        self.images_map: dict[str, Path] = {}

        images_json = sample_dir / "images.json"
        if images_json.exists():
            entries = json.loads(images_json.read_text(encoding="utf-8"))
            for entry in entries:
                orig_url = entry["original_url"]
                filepath = sample_dir / "images" / entry["filename"]
                if filepath.exists():
                    self.images_map[orig_url] = filepath

    def fetch(
        self,
        url: str,
        *,
        max_size_bytes: int = 5 * 1024 * 1024,
        timeout: float = 10.0,
    ) -> FetchedResource:
        if url == self.requested_url:
            page_path = self.sample_dir / "page.html"
            if not page_path.exists():
                raise FetchError(f"Snapshot page not found at {page_path}")
            content = page_path.read_bytes()
            return FetchedResource(
                url=url,
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=content,
            )

        if url in self.images_map:
            img_path = self.images_map[url]
            content = img_path.read_bytes()
            ext = img_path.suffix.lstrip(".").lower()
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            return FetchedResource(
                url=url,
                status_code=200,
                headers={"content-type": mime},
                content=content,
            )

        raise FetchError(f"Resource {url} not found in snapshot")


MANIFEST_SAMPLES = load_manifest_samples()


@pytest.mark.skipif(
    len(MANIFEST_SAMPLES) == 0, reason="No samples configured in manifest"
)
@pytest.mark.parametrize("slug,info", MANIFEST_SAMPLES)
def test_sample_snapshot(slug: str, info: dict[str, Any]) -> None:
    sample_dir = get_samples_dir() / slug
    if not sample_dir.exists():
        pytest.skip(f"Snapshot directory for '{slug}' not found at {sample_dir}")

    url = info["url"]
    fetcher = SnapshotFetcher(sample_dir, url)
    page_resource = fetcher.fetch(url)

    recipe, warnings = extract_recipe(
        page_resource.text,
        url=url,
        fetcher=fetcher,
        download_images=True,
    )

    if "title" in info:
        assert info["title"].lower() in recipe.title.lower()
    if "min_ingredients" in info:
        assert len(recipe.ingredients) >= info["min_ingredients"]
    if "min_steps" in info:
        assert len(recipe.steps) >= info["min_steps"]


@pytest.mark.live
@pytest.mark.skipif(
    len(MANIFEST_SAMPLES) == 0, reason="No samples configured in manifest"
)
@pytest.mark.parametrize("slug,info", MANIFEST_SAMPLES)
def test_sample_live(slug: str, info: dict[str, Any]) -> None:
    url = info["url"]
    fetcher = SafeFetcher()
    page_resource = fetcher.fetch(url)

    recipe, warnings = extract_recipe(
        page_resource.text,
        url=url,
        fetcher=fetcher,
        download_images=True,
    )

    if "title" in info:
        assert info["title"].lower() in recipe.title.lower()
    if "min_ingredients" in info:
        assert len(recipe.ingredients) >= info["min_ingredients"]
    if "min_steps" in info:
        assert len(recipe.steps) >= info["min_steps"]
