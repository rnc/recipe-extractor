# SPDX-License-Identifier: Apache-2.0
"""Recipe extraction wrapper around recipe-scrapers and Schema.org metadata."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from recipe_scrapers import scrape_html

from recipe_extractor.fetch import Fetcher
from recipe_extractor.images import discover_image_urls, fetch_and_embed_images
from recipe_extractor.models import Ingredient, Recipe, RecipeImage, Step
from recipe_extractor.units import convert_recipe, parse_ingredient_line

logger = logging.getLogger(__name__)

CLUTTER_TEXT_PATTERNS = [
    r"^\s*(?:rate|review)\s+this\s+recipe\b",
    r"^\s*leave\s+a\s+(?:comment|review)\b",
    r"^\s*pin\s+(?:this\s+recipe|for\s+later)\b",
    r"^\s*follow\s+us\s+on\b",
    r"^\s*sign\s+up\s+for\b",
    r"^\s*jump\s+to\s+recipe\b",
    r"^\s*print\s+(?:this\s+)?recipe\b",
    r"^\s*nutrition\s+(?:facts|information)\b",
    r"^\s*did\s+you\s+make\s+this\b",
    r"^\s*share\s+your\s+photo\b",
]


def is_clutter_text(text: str) -> bool:
    """Check if a line of text is a promotional / social media clutter line."""
    text_clean = text.strip().lower()
    return any(re.search(pattern, text_clean) for pattern in CLUTTER_TEXT_PATTERNS)


def _safe_call(fn: Any, default: Any = None) -> Any:
    """Safely call a scraper method, returning default on exception."""
    try:
        val = fn()
        return val if val is not None else default
    except Exception:
        return default


def extract_recipe(
    html: str,
    url: str = "",
    *,
    fetcher: Fetcher | None = None,
    download_images: bool = True,
    unit_system: Literal["original", "metric", "uk"] = "original",
) -> tuple[Recipe, list[str]]:
    """Extract a canonical Recipe object from HTML content and an optional URL."""
    warnings: list[str] = []
    effective_url = url or "https://example.com/recipe"

    try:
        scraper = scrape_html(
            html,
            org_url=effective_url,
            supported_only=False,
        )
    except Exception as e:
        raise ValueError(f"Could not parse recipe from HTML: {e}") from e

    # Extract basic metadata
    title = str(_safe_call(scraper.title, "")).strip()
    servings = _safe_call(scraper.yields, None)
    if servings is not None:
        servings = str(servings).strip()

    total_time = _safe_call(scraper.total_time, None)
    prep_time = _safe_call(scraper.prep_time, None)
    cook_time = _safe_call(scraper.cook_time, None)

    # Extract ingredients (with groups if available)
    raw_ing_entries: list[tuple[str, str | None]] = []
    groups = _safe_call(scraper.ingredient_groups, [])
    if groups:
        for grp in groups:
            grp_purpose = getattr(grp, "purpose", None)
            grp_items = getattr(grp, "ingredients", [])
            for item in grp_items:
                if isinstance(item, str) and item.strip() and not is_clutter_text(item):
                    raw_ing_entries.append((item.strip(), grp_purpose or None))

    if not raw_ing_entries:
        raw_ingredients = _safe_call(scraper.ingredients, [])
        for item in raw_ingredients:
            if isinstance(item, str) and item.strip() and not is_clutter_text(item):
                raw_ing_entries.append((item.strip(), None))

    ingredients: list[Ingredient] = []
    for raw_line, grp in raw_ing_entries:
        parsed = parse_ingredient_line(raw_line)
        ingredients.append(
            Ingredient(
                raw=raw_line,
                quantity=parsed.quantity,
                unit=parsed.unit,
                name=parsed.name,
                note=parsed.note,
                group=grp,
                original_raw=raw_line,
            )
        )

    # Extract instructions / steps
    steps: list[Step] = []
    raw_step_texts: list[str] = []
    instruction_list = _safe_call(scraper.instructions_list, [])
    if instruction_list:
        for inst in instruction_list:
            if isinstance(inst, str) and inst.strip() and not is_clutter_text(inst):
                raw_step_texts.append(inst.strip())
    else:
        instructions_text = _safe_call(scraper.instructions, "")
        if instructions_text:
            for line in instructions_text.splitlines():
                if line.strip() and not is_clutter_text(line):
                    raw_step_texts.append(line.strip())

    for txt in raw_step_texts:
        steps.append(Step(text=txt))

    # Extract notes or description
    notes: list[str] = []
    description = _safe_call(scraper.description, "")
    if description and isinstance(description, str) and description.strip():
        # Keep short description as initial note if available
        notes.append(description.strip())

    # Extract images
    discovered_images = discover_image_urls(html, base_url=url, fetcher=fetcher)
    scraper_img = _safe_call(scraper.image, None)
    if (
        scraper_img
        and isinstance(scraper_img, str)
        and scraper_img.strip()
        and scraper_img.strip() not in discovered_images
    ):
        discovered_images.insert(0, scraper_img.strip())

    recipe_images: list[RecipeImage] = []
    if discovered_images:
        if download_images and fetcher is not None:
            downloaded, img_warnings = fetch_and_embed_images(
                discovered_images, fetcher
            )
            recipe_images.extend(downloaded)
            warnings.extend(img_warnings)

        # Fallback if download was disabled or failed to produce images
        if not recipe_images:
            for idx, img_url in enumerate(discovered_images[:5]):
                recipe_images.append(
                    RecipeImage(
                        src=img_url,
                        alt=f"Recipe photo {idx + 1}",
                        selected=(idx == 0),
                        original_url=img_url,
                    )
                )

    recipe = Recipe(
        title=title or "Untitled Recipe",
        source_url=url or None,
        servings=servings,
        prep_time_minutes=prep_time if isinstance(prep_time, int) else None,
        cook_time_minutes=cook_time if isinstance(cook_time, int) else None,
        total_time_minutes=total_time if isinstance(total_time, int) else None,
        images=recipe_images,
        ingredients=ingredients,
        steps=steps,
        notes=notes,
        unit_system="original",
    )

    if unit_system != "original":
        recipe = convert_recipe(recipe, unit_system)

    return recipe, warnings
