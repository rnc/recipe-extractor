# SPDX-License-Identifier: Apache-2.0
"""Unit conversion engine for weights, volumes, temperatures, and UK vocabulary."""

from __future__ import annotations

import json
import logging
import re
from importlib import resources
from typing import Any, Literal

from recipe_extractor.models import Ingredient, Recipe, Step
from recipe_extractor.units.parse import (
    ParsedIngredientResult,
    parse_fraction_or_float,
    parse_ingredient_line,
)

logger = logging.getLogger(__name__)

UnitSystemType = Literal["original", "metric", "uk"]

# Standard culinary oven temperature mapping: F -> (conv_C, fan_C, gas_mark)
STANDARD_OVEN_TEMPS: dict[int, tuple[int, int, str]] = {
    225: (110, 90, "1/4"),
    250: (120, 100, "1/2"),
    275: (140, 120, "1"),
    300: (150, 130, "2"),
    325: (165, 145, "3"),
    350: (180, 160, "4"),
    375: (190, 170, "5"),
    400: (200, 180, "6"),
    425: (220, 200, "7"),
    450: (230, 210, "8"),
    475: (240, 220, "9"),
    500: (260, 240, "10"),
}


def _load_json_data(filename: str) -> dict[str, Any]:
    """Load JSON dataset from the units/data directory."""
    try:
        data_file = resources.files("recipe_extractor.units.data").joinpath(filename)
        return json.loads(data_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except Exception as e:
        logger.warning("Could not load %s from package resources: %e", filename, e)
        return {}


DENSITIES: dict[str, float] = _load_json_data("densities.json")
UK_VOCAB: dict[str, str] = _load_json_data("uk_vocab.json")


def round_culinary_weight(grams: float) -> str:
    """Round grams to sensible culinary precision."""
    if grams <= 0:
        return "0g"
    if grams < 10:
        return f"{round(grams, 1):g}g"
    if grams < 50:
        # Standard rounding for small weights (e.g. 28.35g -> 30g or 28g)
        rounded = round(grams)
        return f"{rounded}g"
    if grams < 1000:
        # Standard culinary rounding (e.g. 113.4g -> 115g, 453.6g -> 450g)
        if grams >= 400:
            rounded = int(round(grams / 25.0) * 25)
        elif grams >= 100:
            rounded = int(round(grams / 5.0) * 5)
        else:
            rounded = int(round(grams / 5.0) * 5)
        return f"{rounded}g"
    # Over 1kg
    kg = grams / 1000.0
    if kg == round(kg):
        return f"{int(kg)}kg"
    return f"{round(kg, 2):g}kg"


def round_culinary_volume(ml: float) -> str:
    """Round millilitres to sensible culinary precision."""
    if ml <= 0:
        return "0ml"
    if ml < 15:
        return f"{round(ml, 1):g}ml"
    if ml < 100:
        rounded = int(round(ml / 5.0) * 5)
        return f"{rounded}ml"
    if ml < 1000:
        # Round to nearest 5ml or 10ml
        rounded = int(round(ml / 5.0) * 5)
        return f"{rounded}ml"
    # Litres
    litres = ml / 1000.0
    if litres == round(litres):
        return f"{int(litres)}L"
    return f"{round(litres, 2):g}L"


def find_ingredient_density(ingredient_name: str | None) -> float | None:
    """Lookup ingredient density in grams per cup."""
    if not ingredient_name:
        return None

    name_lower = ingredient_name.lower().strip()
    name_clean = re.sub(r"[^\w\s-]", "", name_lower)

    # Exact match
    if name_clean in DENSITIES:
        return DENSITIES[name_clean]

    # Check key containment (longest match first)
    sorted_keys = sorted(DENSITIES.keys(), key=len, reverse=True)
    for key in sorted_keys:
        # Word boundary match
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, name_clean):
            return DENSITIES[key]

    return None


def apply_uk_vocabulary(text: str) -> str:
    """Translate US culinary terms in text to UK equivalents."""
    result = text
    # Sort terms by length descending to replace compound terms first
    sorted_vocab = sorted(UK_VOCAB.keys(), key=len, reverse=True)
    for us_term in sorted_vocab:
        uk_term = UK_VOCAB[us_term]
        pattern = rf"\b{re.escape(us_term)}\b"
        result = re.sub(pattern, uk_term, result, flags=re.IGNORECASE)
    return result


def convert_fahrenheit_to_celsius(f_temp: float) -> tuple[int, int, str | None]:
    """Convert Fahrenheit to (celsius_conventional, celsius_fan, gas_mark)."""
    f_int = int(round(f_temp))
    # Check standard culinary temperatures table first
    if f_int in STANDARD_OVEN_TEMPS:
        return STANDARD_OVEN_TEMPS[f_int]

    # Check nearest standard oven temperature if within 5 degrees
    f_round_25 = int(round(f_temp / 25.0) * 25)
    if abs(f_temp - f_round_25) <= 5 and f_round_25 in STANDARD_OVEN_TEMPS:
        return STANDARD_OVEN_TEMPS[f_round_25]

    c_exact = (f_temp - 32.0) * 5.0 / 9.0
    c_conv = int(round(c_exact / 5.0) * 5)
    c_fan = max(0, c_conv - 20)
    return c_conv, c_fan, None


def convert_text_temperatures(text: str, target_system: UnitSystemType) -> str:
    """Detect and convert temperatures in instructions / step text."""
    if target_system == "original":
        return text

    def _replace_f(match: re.Match[str]) -> str:
        temp_str = match.group("temp")
        try:
            f_val = float(temp_str)
        except ValueError:
            return match.group(0)

        # Ignore unrealistic baking temperatures
        if f_val < 150 or f_val > 600:
            return match.group(0)

        c_conv, _c_fan, gas_mark = convert_fahrenheit_to_celsius(f_val)
        if target_system == "uk" and gas_mark:
            return f"{c_conv}°C (Gas Mark {gas_mark})"
        return f"{c_conv}°C"

    # Match patterns like: 350°F, 350 °F, 350F, 350 degrees F, 350 degrees Fahrenheit
    f_pattern = r"\b(?P<temp>\d{3})\s*(?:°|º|deg|degrees)?\s*(?:F\b|fahrenheit\b|°F\b)"
    return re.sub(f_pattern, _replace_f, text, flags=re.IGNORECASE)


def convert_text_dimensions(text: str, target_system: UnitSystemType) -> str:
    """Detect and convert imperial pan dimensions/lengths (e.g. 9-inch) to cm."""
    if target_system == "original":
        return text

    # Pattern for 2D pan size e.g. 9x13-inch, 8 x 8 inch, 9x9"
    def _replace_2d_dim(match: re.Match[str]) -> str:
        w_str = match.group("w")
        h_str = match.group("h")
        try:
            w_cm = int(round(float(w_str) * 2.54))
            h_cm = int(round(float(h_str) * 2.54))
            return f"{w_cm}x{h_cm}cm"
        except ValueError:
            return match.group(0)

    p2d = (
        r"\b(?P<w>\d+(?:\.\d+)?)\s*(?:x|×|\*)\s*(?P<h>\d+(?:\.\d+)?)"
        r"\s*(?:-|–|\s)?\s*(?:inch|inches|\")\b"
    )
    text = re.sub(p2d, _replace_2d_dim, text, flags=re.IGNORECASE)

    # Pattern for 1D dimension e.g. 9-inch, 12 inch
    def _replace_1d_dim(match: re.Match[str]) -> str:
        d_str = match.group("d")
        try:
            d_cm = int(round(float(d_str) * 2.54))
            return f"{d_cm}cm"
        except ValueError:
            return match.group(0)

    p1d = r"\b(?P<d>\d+(?:\.\d+)?)\s*(?:-|–|\s)?\s*(?:inch|inches|\")\b"
    text = re.sub(p1d, _replace_1d_dim, text, flags=re.IGNORECASE)

    return text


def convert_text_units(text: str, target_system: UnitSystemType) -> str:
    """Convert temperatures, dimensions, and UK vocabulary in text."""
    if target_system == "original":
        return text

    converted = convert_text_temperatures(text, target_system)
    converted = convert_text_dimensions(converted, target_system)

    if target_system == "uk":
        converted = apply_uk_vocabulary(converted)

    return converted


def convert_ingredient(
    ingredient: Ingredient,
    target_system: UnitSystemType,
    *,
    source_cup_ml: float = 240.0,
) -> Ingredient:
    """Convert a single Ingredient object to the specified unit system."""
    effective_system = ingredient.unit_override or target_system

    # Ensure original_raw is preserved
    original_text = ingredient.original_raw or ingredient.raw

    if effective_system == "original":
        return ingredient.model_copy(
            update={
                "converted": None,
                "original_raw": original_text,
            }
        )

    # Parse ingredient structured fields if missing
    parsed: ParsedIngredientResult
    if (
        ingredient.quantity is not None
        and ingredient.unit is not None
        and ingredient.name is not None
    ):
        parsed = ParsedIngredientResult(
            raw=original_text,
            quantity=ingredient.quantity,
            unit=ingredient.unit,
            name=ingredient.name,
            note=ingredient.note,
        )
    else:
        parsed = parse_ingredient_line(original_text)

    # Extract quantity value
    q_val: float | None = None
    if isinstance(parsed.quantity, (int, float)):
        q_val = float(parsed.quantity)
    elif isinstance(parsed.quantity, str):
        q_val = parse_fraction_or_float(parsed.quantity)

    unit = (parsed.unit or "").lower().strip().rstrip(".")
    name = parsed.name or ""
    note = parsed.note or ""

    # Apply UK vocabulary translation if UK mode
    if effective_system == "uk":
        name = apply_uk_vocabulary(name)
        if note:
            note = apply_uk_vocabulary(note)

    # If neither quantity nor unit exists, return translated text
    if q_val is None and not parsed.quantity and not unit:
        converted_line = f"{name}, {note}" if note else name
        return ingredient.model_copy(
            update={
                "converted": converted_line if converted_line else original_text,
                "original_raw": original_text,
            }
        )

    converted_qty_str: str | None = None

    # Handle countable items with quantity but no unit (e.g. "4 shallots")
    if not unit:
        if q_val is not None:
            converted_qty_str = f"{round(q_val, 2):g}"
        elif isinstance(parsed.quantity, str):
            converted_qty_str = parsed.quantity
        else:
            converted_qty_str = ""

    # Handle Butter sticks
    if unit in ("stick", "sticks"):
        if q_val is not None:
            grams = q_val * 113.4
            converted_qty_str = round_culinary_weight(grams)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Weight (oz, lb)
    elif unit in ("oz", "ounce", "ounces"):
        if q_val is not None:
            grams = q_val * 28.3495
            converted_qty_str = round_culinary_weight(grams)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    elif unit in ("lb", "lbs", "pound", "pounds"):
        if q_val is not None:
            grams = q_val * 453.592
            converted_qty_str = round_culinary_weight(grams)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Volume (cups)
    elif unit in ("cup", "cups", "c"):
        if q_val is not None:
            # Check density table for volume-to-weight
            density = find_ingredient_density(parsed.name or name)
            if density is not None:
                grams = q_val * density
                converted_qty_str = round_culinary_weight(grams)
                unit = ""
            else:
                # Fallback to volume in ml
                cup_ml = 250.0 if effective_system == "uk" else source_cup_ml
                ml = q_val * cup_ml
                converted_qty_str = round_culinary_volume(ml)
                unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Fluid Ounces
    elif unit in ("fl oz", "fluid ounce", "fluid ounces"):
        if q_val is not None:
            ml = q_val * 29.5735
            converted_qty_str = round_culinary_volume(ml)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Pints
    elif unit in ("pint", "pints", "pt"):
        if q_val is not None:
            # US pint = 473ml, UK pint = 568ml
            pint_ml = 568.26 if effective_system == "uk" else 473.176
            ml = q_val * pint_ml
            converted_qty_str = round_culinary_volume(ml)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Quarts
    elif unit in ("quart", "quarts", "qt"):
        if q_val is not None:
            ml = q_val * 946.353
            converted_qty_str = round_culinary_volume(ml)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Gallons
    elif unit in ("gallon", "gallons", "gal"):
        if q_val is not None:
            litres = q_val * 3.78541
            converted_qty_str = f"{round(litres, 2):g}L"
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    # Handle Tablespoons / Teaspoons
    elif unit in ("tbsp", "tablespoon", "tablespoons", "tbs", "tbl"):
        converted_qty_str = (
            f"{round(q_val, 2):g}" if q_val is not None else str(parsed.quantity or "")
        )
        unit = "tbsp"

    elif unit in ("tsp", "teaspoon", "teaspoons"):
        converted_qty_str = (
            f"{round(q_val, 2):g}" if q_val is not None else str(parsed.quantity or "")
        )
        unit = "tsp"

    # Handle existing metric units (g, kg, ml, l)
    elif unit in ("g", "gram", "grams"):
        if q_val is not None:
            converted_qty_str = round_culinary_weight(q_val)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    elif unit in ("kg", "kilogram", "kilograms"):
        if q_val is not None:
            converted_qty_str = round_culinary_weight(q_val * 1000.0)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    elif unit in ("ml", "milliliter", "milliliters", "millilitre", "millilitres"):
        if q_val is not None:
            converted_qty_str = round_culinary_volume(q_val)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    elif unit in ("l", "liter", "liters", "litre", "litres"):
        if q_val is not None:
            converted_qty_str = round_culinary_volume(q_val * 1000.0)
            unit = ""
        else:
            converted_qty_str = str(parsed.quantity or "")

    else:
        # Unknown/container unit (e.g. pinch, clove, can) -> keep quantity and unit
        if q_val is not None:
            converted_qty_str = f"{round(q_val, 2):g}"
        elif isinstance(parsed.quantity, str):
            converted_qty_str = parsed.quantity
        else:
            converted_qty_str = ""

    # Build converted line
    parts: list[str] = []
    if converted_qty_str:
        if unit:
            parts.append(f"{converted_qty_str} {unit}")
        else:
            parts.append(converted_qty_str)
    if name:
        parts.append(name)
    line_body = " ".join(parts).strip()
    if note:
        line_body = f"{line_body}, {note}"

    return ingredient.model_copy(
        update={
            "quantity": parsed.quantity,
            "unit": parsed.unit,
            "name": name or parsed.name,
            "note": note or parsed.note,
            "converted": line_body,
            "original_raw": original_text,
        }
    )


def convert_recipe(
    recipe: Recipe,
    target_system: UnitSystemType,
) -> Recipe:
    """Convert an entire Recipe to the target unit system."""
    converted_ingredients = [
        convert_ingredient(ing, target_system) for ing in recipe.ingredients
    ]

    converted_steps: list[Step] = []
    for step in recipe.steps:
        new_text = convert_text_units(step.text, target_system)
        converted_steps.append(Step(text=new_text))

    converted_notes: list[str] = [
        convert_text_units(note, target_system) for note in recipe.notes
    ]

    return recipe.model_copy(
        update={
            "ingredients": converted_ingredients,
            "steps": converted_steps,
            "notes": converted_notes,
            "unit_system": target_system,
        }
    )
