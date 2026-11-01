# SPDX-License-Identifier: Apache-2.0
"""Ingredient string parsing and quantity extraction."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

logger = logging.getLogger(__name__)

# Unicode fraction mapping
UNICODE_FRACTIONS: dict[str, str] = {
    "¼": "1/4",
    "½": "1/2",
    "¾": "3/4",
    "⅐": "1/7",
    "⅑": "1/9",
    "⅒": "1/10",
    "⅓": "1/3",
    "⅔": "2/3",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

# Common cooking units for regex fallback
KNOWN_UNITS = [
    # Weight
    "g",
    "gram",
    "grams",
    "kg",
    "kilogram",
    "kilograms",
    "oz",
    "ounce",
    "ounces",
    "lb",
    "lbs",
    "pound",
    "pounds",
    # Volume
    "cup",
    "cups",
    "c",
    "c.",
    "ml",
    "milliliter",
    "milliliters",
    "millilitre",
    "millilitres",
    "l",
    "liter",
    "liters",
    "litre",
    "litres",
    "dl",
    "deciliter",
    "deciliters",
    "fl oz",
    "fluid ounce",
    "fluid ounces",
    "tbsp",
    "tablespoon",
    "tablespoons",
    "tbs",
    "tbl",
    "tsp",
    "teaspoon",
    "teaspoons",
    "pt",
    "pint",
    "pints",
    "qt",
    "quart",
    "quarts",
    "gal",
    "gallon",
    "gallons",
    # Baking / Container units
    "stick",
    "sticks",
    "pinch",
    "pinches",
    "dash",
    "dashes",
    "drop",
    "drops",
    "clove",
    "cloves",
    "can",
    "cans",
    "package",
    "packages",
    "pkg",
    "slice",
    "slices",
    "piece",
    "pieces",
    "head",
    "heads",
    "bunch",
    "bunches",
    "stalk",
    "stalks",
    "sprig",
    "sprigs",
    "handful",
    "handfuls",
]


@dataclass
class ParsedIngredientResult:
    """Structured fields parsed from an ingredient line."""

    raw: str
    quantity: float | str | None = None
    quantity_min: float | None = None
    quantity_max: float | None = None
    unit: str | None = None
    name: str | None = None
    note: str | None = None


def normalize_fractions(text: str) -> str:
    """Normalize unicode vulgar fractions to ascii representations."""
    result = text
    for char, replacement in UNICODE_FRACTIONS.items():
        if char in result:
            # If preceded by a digit, ensure space e.g. "1½" -> "1 1/2"
            result = re.sub(rf"(\d){char}", rf"\1 {replacement}", result)
            result = result.replace(char, replacement)
    return unicodedata.normalize("NFKC", result)


def parse_fraction_or_float(val: str) -> float | None:
    """Parse a string containing a float, integer, fraction, or mixed number."""
    val = val.strip()
    if not val:
        return None

    # Handle mixed number e.g. "1 1/2"
    if " " in val:
        parts = val.split()
        if len(parts) == 2:
            try:
                whole = float(parts[0])
                frac = float(Fraction(parts[1]))
                return whole + frac
            except (ValueError, ZeroDivisionError):
                pass

    # Handle single fraction e.g. "1/2"
    if "/" in val:
        try:
            return float(Fraction(val))
        except (ValueError, ZeroDivisionError):
            pass

    # Handle simple float / int
    try:
        return float(val)
    except ValueError:
        return None


def _clean_text(text: str) -> str:
    """Clean extra spaces and trailing punctuation."""
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(",.- ")
    return text


def _fallback_parse(line: str) -> ParsedIngredientResult:
    """Regex-based deterministic parser for ingredient lines."""
    normalized = normalize_fractions(line.strip())

    # Check for range: e.g. "1-2 cups flour" or "1 to 2 cups flour"
    range_match = re.match(
        r"^(?P<qmin>\d+(?:\.\d+)?|\d+\s+\d+/\d+|\d+/\d+)\s*(?:-|to|–|—)\s*"
        r"(?P<qmax>\d+(?:\.\d+)?|\d+\s+\d+/\d+|\d+/\d+)\s+"
        r"(?P<rest>.+)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if range_match:
        qmin_str = range_match.group("qmin")
        qmax_str = range_match.group("qmax")
        rest = range_match.group("rest")
        qmin = parse_fraction_or_float(qmin_str)
        qmax = parse_fraction_or_float(qmax_str)
        quantity_str = f"{qmin_str}-{qmax_str}"

        unit, name, note = _split_unit_name_note(rest)
        return ParsedIngredientResult(
            raw=line,
            quantity=quantity_str,
            quantity_min=qmin,
            quantity_max=qmax,
            unit=unit,
            name=name,
            note=note,
        )

    # Check for single quantity: e.g. "2 cups flour" or "1 1/2 tbsp vanilla"
    single_match = re.match(
        r"^(?P<q>\d+(?:\.\d+)?|\d+\s+\d+/\d+|\d+/\d+)\s*(?P<rest>.*)$",
        normalized,
    )
    if single_match:
        q_str = single_match.group("q")
        rest = single_match.group("rest")
        q_val = parse_fraction_or_float(q_str)
        unit, name, note = _split_unit_name_note(rest)
        return ParsedIngredientResult(
            raw=line,
            quantity=q_val if q_val is not None else q_str,
            quantity_min=q_val,
            quantity_max=q_val,
            unit=unit,
            name=name,
            note=note,
        )

    # No leading quantity found
    unit, name, note = _split_unit_name_note(normalized)
    return ParsedIngredientResult(
        raw=line,
        quantity=None,
        quantity_min=None,
        quantity_max=None,
        unit=unit,
        name=name or line,
        note=note,
    )


def _split_unit_name_note(
    text: str,
) -> tuple[str | None, str | None, str | None]:
    """Split remainder of string into unit, name, and preparation note."""
    text = text.strip()
    if not text:
        return None, None, None

    # Check for unit at the start of text
    unit: str | None = None
    rest = text

    # Sort units by length descending so "fluid ounces" matches before "ounces"
    for u in sorted(KNOWN_UNITS, key=len, reverse=True):
        pattern = rf"^(?:of\s+)?\b{re.escape(u)}\b(?:\s+of)?(?:\s+(.*))?$"
        m = re.match(pattern, rest, flags=re.IGNORECASE)
        if m:
            unit = u
            rest = m.group(1) or ""
            break

    # Extract note (e.g. after comma, or inside parentheses)
    note: str | None = None
    name = rest

    # Parentheses note e.g. "butter (softened)" or "sugar (about 1 cup)"
    paren_match = re.search(r"\(([^)]+)\)", name)
    if paren_match:
        paren_content = paren_match.group(1)
        name = name.replace(paren_match.group(0), " ").strip()
        note = paren_content

    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        name = parts[0]
        comma_note = parts[1]
        note = f"{note}, {comma_note}" if note else comma_note

    clean_name = _clean_text(name)
    clean_note = _clean_text(note) if note else None
    return unit, clean_name or None, clean_note


def parse_ingredient_line(line: str) -> ParsedIngredientResult:
    """Parse an ingredient line into structured fields."""
    raw = line.strip()
    if not raw:
        return ParsedIngredientResult(raw="")

    try:
        import ingredient_parser

        parsed = ingredient_parser.parse_ingredient(raw)
        # Extract name
        name_parts = getattr(parsed, "name", None)
        name: str | None = None
        if name_parts:
            if isinstance(name_parts, list):
                name = " ".join(
                    getattr(p, "text", str(p)) for p in name_parts if p
                ).strip()
            else:
                name = getattr(name_parts, "text", str(name_parts)).strip()

        # Extract amount / quantity / unit
        amounts = getattr(parsed, "amount", [])
        quantity: float | str | None = None
        q_min: float | None = None
        q_max: float | None = None
        unit: str | None = None

        if amounts and len(amounts) > 0:
            first_amt = amounts[0]
            amt_unit = getattr(first_amt, "unit", None)
            if amt_unit is not None:
                unit = getattr(amt_unit, "name", str(amt_unit))
                if unit == "dimensionless" or not unit:
                    unit = None

            q_raw = getattr(first_amt, "quantity", None)
            q_max_raw = getattr(first_amt, "quantity_max", None)

            if isinstance(q_raw, (Fraction, int, float)):
                q_min = float(q_raw)

            if isinstance(q_max_raw, (Fraction, int, float)):
                q_max = float(q_max_raw)

            is_range = getattr(first_amt, "RANGE", False)
            if is_range and q_min is not None and q_max is not None and q_min != q_max:
                quantity = f"{q_min:g}-{q_max:g}"
            elif q_min is not None:
                quantity = q_min

        # Extract preparation / comment
        prep = getattr(parsed, "preparation", None)
        comment = getattr(parsed, "comment", None)
        notes: list[str] = []
        if prep:
            prep_text = getattr(prep, "text", str(prep)).strip()
            if prep_text:
                notes.append(prep_text)
        if comment:
            comment_text = getattr(comment, "text", str(comment)).strip()
            if comment_text:
                notes.append(comment_text)

        note_str = ", ".join(notes) if notes else None

        if name:
            return ParsedIngredientResult(
                raw=raw,
                quantity=quantity,
                quantity_min=q_min,
                quantity_max=q_max,
                unit=unit,
                name=_clean_text(name) or None,
                note=_clean_text(note_str) if note_str else None,
            )
    except Exception as e:
        logger.debug("ingredient_parser error on '%s': %s; using fallback", raw, e)

    # Fallback to regex tokenizer
    return _fallback_parse(raw)
