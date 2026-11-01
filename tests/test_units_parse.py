# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ingredient parsing and quantity extraction."""

from recipe_extractor.units.parse import (
    normalize_fractions,
    parse_fraction_or_float,
    parse_ingredient_line,
)


def test_normalize_fractions() -> None:
    assert normalize_fractions("1½ cups") == "1 1/2 cups"
    assert normalize_fractions("¼ tsp salt") == "1/4 tsp salt"
    assert normalize_fractions("¾ cup sugar") == "3/4 cup sugar"
    assert normalize_fractions("2 ⅓ tbsp") == "2 1/3 tbsp"


def test_parse_fraction_or_float() -> None:
    assert parse_fraction_or_float("2") == 2.0
    assert parse_fraction_or_float("1.5") == 1.5
    assert parse_fraction_or_float("1/2") == 0.5
    assert parse_fraction_or_float("1 1/2") == 1.5
    assert parse_fraction_or_float("3/4") == 0.75
    assert parse_fraction_or_float("invalid") is None


def test_parse_ingredient_standard() -> None:
    res = parse_ingredient_line("2 cups all-purpose flour, sifted")
    assert res.quantity == 2.0 or res.quantity == "2"
    assert res.unit is not None and "cup" in res.unit.lower()
    assert res.name is not None and "flour" in res.name.lower()
    assert res.note is not None and "sifted" in res.note.lower()


def test_parse_ingredient_fractions() -> None:
    res = parse_ingredient_line("1 1/2 tsp vanilla extract")
    assert res.quantity == 1.5 or res.quantity == "1.5" or res.quantity == "1 1/2"
    assert res.unit is not None and (
        "tsp" in res.unit.lower() or "teaspoon" in res.unit.lower()
    )
    assert res.name is not None and "vanilla" in res.name.lower()


def test_parse_ingredient_unicode_fraction() -> None:
    res = parse_ingredient_line("½ cup unsalted butter, softened")
    assert res.quantity == 0.5 or res.quantity == "0.5" or res.quantity == "1/2"
    assert res.unit is not None and "cup" in res.unit.lower()
    assert res.name is not None and "butter" in res.name.lower()
    assert res.note is not None and "softened" in res.note.lower()


def test_parse_ingredient_range() -> None:
    res = parse_ingredient_line("2-3 cloves garlic, minced")
    assert res.quantity is not None
    assert "2" in str(res.quantity)
    assert res.name is not None and "garlic" in res.name.lower()
    assert res.note is not None and "minced" in res.note.lower()


def test_parse_ingredient_no_unit() -> None:
    res = parse_ingredient_line("3 large eggs, beaten")
    assert res.quantity == 3.0 or res.quantity == "3"
    assert res.name is not None and "egg" in res.name.lower()
    assert res.note is not None and "beaten" in res.note.lower()


def test_parse_ingredient_no_quantity() -> None:
    res = parse_ingredient_line("Salt and freshly ground black pepper to taste")
    assert res.quantity is None
    assert "salt" in (res.name or res.raw).lower()
