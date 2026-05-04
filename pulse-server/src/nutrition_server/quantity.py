from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Density-free volume→gram approximations. Solid foods deviate; treated as best-effort.
_GRAMS_PER_UNIT: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "cup": 240.0,
    "cups": 240.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "fl oz": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
}

_COUNT_UNITS: set[str] = {
    "serving",
    "servings",
    "piece",
    "pieces",
    "slice",
    "slices",
    "wrap",
    "wraps",
    "sandwich",
    "sandwiches",
    "item",
    "items",
    "egg",
    "eggs",
    "whole",
    "medium",
    "small",
    "large",
    "unit",
    "units",
    "scoop",
    "scoops",
    "bar",
    "bars",
    "stick",
    "sticks",
    "can",
    "cans",
    "bottle",
    "bottles",
}

_FRACTION_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_MIXED_RE = re.compile(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$")
# Splits "150g", "1.5 kg", "1 1/2 cups", "1/2 cup", "3" → (value_str, unit_str).
_VALUE_UNIT_RE = re.compile(
    r"^\s*(?P<value>\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*(?P<unit>.*)$"
)


@dataclass
class ParsedQuantity:
    value: float
    unit: str
    grams: float | None  # None when unit is count-based or unknown
    is_count: bool
    raw: str


def _parse_value(token: str) -> float | None:
    token = token.strip()
    mixed = _MIXED_RE.match(token)
    if mixed:
        whole, num, denom = mixed.groups()
        return float(whole) + float(num) / float(denom)
    frac = _FRACTION_RE.match(token)
    if frac:
        num, denom = frac.groups()
        return float(num) / float(denom)
    try:
        return float(token)
    except ValueError:
        return None


def parse_quantity(text: str) -> ParsedQuantity:
    """Best-effort free-text quantity parser.

    Returns a `ParsedQuantity` with `grams` filled when the unit is mass/volume-convertible,
    `is_count=True` when the unit is countable but not gram-convertible, and `value=1.0`
    with `is_count=True` when nothing parses (treat as one serving).
    """
    raw = text.strip()
    if not raw:
        return ParsedQuantity(value=1.0, unit="serving", grams=None, is_count=True, raw=text)

    lowered = raw.lower()
    match = _VALUE_UNIT_RE.match(lowered)
    if match is None:
        # Pure unit ("a wrap"). Fallback: 1 unit.
        return ParsedQuantity(value=1.0, unit=lowered, grams=None, is_count=True, raw=text)

    value = _parse_value(match.group("value"))
    if value is None:
        return ParsedQuantity(value=1.0, unit=lowered, grams=None, is_count=True, raw=text)

    unit_normalized = match.group("unit").strip().rstrip(".")
    if not unit_normalized:
        # Bare number ("3"). Treat as count of servings.
        return ParsedQuantity(value=value, unit="serving", grams=None, is_count=True, raw=text)

    if unit_normalized in _GRAMS_PER_UNIT:
        return ParsedQuantity(
            value=value,
            unit=unit_normalized,
            grams=value * _GRAMS_PER_UNIT[unit_normalized],
            is_count=False,
            raw=text,
        )
    for compound in ("fl oz", "fluid ounce", "fluid ounces"):
        if unit_normalized.startswith(compound):
            return ParsedQuantity(
                value=value,
                unit=compound,
                grams=value * _GRAMS_PER_UNIT[compound],
                is_count=False,
                raw=text,
            )
    if unit_normalized in _COUNT_UNITS or unit_normalized.split()[0] in _COUNT_UNITS:
        return ParsedQuantity(value=value, unit=unit_normalized, grams=None, is_count=True, raw=text)

    # Unknown unit but value parsed — treat as count.
    return ParsedQuantity(value=value, unit=unit_normalized, grams=None, is_count=True, raw=text)


def scale_macros(
    food: dict[str, Any],
    parsed: ParsedQuantity,
) -> tuple[dict[str, Any], str]:
    """Scale per-basis food macros to the parsed quantity.

    `food` must follow the shape returned by `usda.normalize_food_nutrients`:
    - calories, protein_g, carbs_g, fat_g (numeric)
    - serving_size (float | None), serving_size_unit (str | None)

    Returns `(scaled_macros, confidence)` where confidence is "high" / "medium" / "low".

    Convention:
    - Branded foods: macros are per `serving_size` `serving_size_unit`. We convert that basis
      to grams via the unit table (high confidence when convertible, low otherwise).
    - SR Legacy / Foundation: no `serving_size` → macros are per 100g (USDA standard).
    """
    base_calories = food.get("calories") or 0
    base_protein = food.get("protein_g") or 0.0
    base_carbs = food.get("carbs_g") or 0.0
    base_fat = food.get("fat_g") or 0.0

    serving_size = food.get("serving_size")
    serving_unit = (food.get("serving_size_unit") or "").strip().lower()

    basis_grams: float | None = None
    confidence = "high"

    if serving_size and serving_unit and serving_unit in _GRAMS_PER_UNIT:
        basis_grams = float(serving_size) * _GRAMS_PER_UNIT[serving_unit]
    elif serving_size and serving_unit:
        # Branded with a non-mass serving unit ("1 wrap", "1 bar"). Treat the per-basis macros as one count.
        basis_grams = None
    else:
        basis_grams = 100.0  # SR/Foundation default

    # Compute multiplier
    if parsed.grams is not None and basis_grams is not None:
        multiplier = parsed.grams / basis_grams
    elif parsed.is_count and serving_size and not (serving_unit in _GRAMS_PER_UNIT):
        # Count-based food (1 wrap), user said "1 wrap" → multiplier = value
        multiplier = parsed.value
        confidence = "medium"
    elif parsed.is_count and basis_grams is not None:
        # User said "1 serving" of an SR food. Assume one serving == one basis (100g or known serving grams).
        multiplier = parsed.value
        confidence = "low"
    else:
        multiplier = parsed.value
        confidence = "low"

    scaled = {
        "calories": int(round(base_calories * multiplier)),
        "protein_g": round(base_protein * multiplier, 1),
        "carbs_g": round(base_carbs * multiplier, 1),
        "fat_g": round(base_fat * multiplier, 1),
    }
    return scaled, confidence
