# SPDX-License-Identifier: Apache-2.0
"""Tests for recipe extraction logic using synthetic fixtures."""

from pathlib import Path

from recipe_extractor.extract import extract_recipe

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_extract_simple_recipe() -> None:
    html = (FIXTURES_DIR / "simple_recipe.html").read_text()
    recipe, warnings = extract_recipe(
        html,
        url="https://example.com/lemon-cake",
        download_images=False,
    )

    assert recipe.title == "Classic Lemon Drizzle Cake"
    assert recipe.servings == "8 servings"
    assert recipe.prep_time_minutes == 15
    assert recipe.cook_time_minutes == 45
    assert recipe.total_time_minutes == 60
    assert len(recipe.ingredients) == 5
    assert recipe.ingredients[0].raw == "225g unsalted butter, softened"
    assert len(recipe.steps) == 3
    assert "Heat the oven to 180C" in recipe.steps[0].text
    assert len(recipe.notes) == 1
    assert "British teatime classic" in recipe.notes[0]
    assert len(recipe.images) >= 2


def test_extract_grouped_recipe() -> None:
    html = (FIXTURES_DIR / "grouped_recipe.html").read_text()
    recipe, warnings = extract_recipe(
        html,
        url="https://example.com/sticky-toffee",
        download_images=False,
    )

    assert recipe.title == "Sticky Toffee Pudding"
    assert recipe.servings is not None and "6" in recipe.servings
    assert len(recipe.ingredients) >= 7
    assert len(recipe.steps) == 4
    assert len(recipe.images) >= 1
