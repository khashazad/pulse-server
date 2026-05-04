from __future__ import annotations

import pytest

from nutrition_server.quantity import parse_quantity, scale_macros


def test_parse_grams_simple() -> None:
    p = parse_quantity("150g")
    assert p.value == 150.0
    assert p.unit == "g"
    assert p.grams == 150.0
    assert p.is_count is False


def test_parse_grams_spaced() -> None:
    p = parse_quantity("150 grams")
    assert p.grams == 150.0


def test_parse_kilograms() -> None:
    p = parse_quantity("1.5 kg")
    assert p.grams == 1500.0


def test_parse_ounces() -> None:
    p = parse_quantity("4 oz")
    assert p.grams == pytest.approx(113.398, rel=1e-3)


def test_parse_cups() -> None:
    p = parse_quantity("2 cups")
    assert p.grams == 480.0


def test_parse_tbsp() -> None:
    p = parse_quantity("3 tbsp")
    assert p.grams == 45.0


def test_parse_fraction() -> None:
    p = parse_quantity("1/2 cup")
    assert p.value == 0.5
    assert p.grams == 120.0


def test_parse_mixed_fraction() -> None:
    p = parse_quantity("1 1/2 cups")
    assert p.value == 1.5
    assert p.grams == 360.0


def test_parse_count_unit() -> None:
    p = parse_quantity("1 wrap")
    assert p.value == 1.0
    assert p.unit == "wrap"
    assert p.is_count is True
    assert p.grams is None


def test_parse_serving() -> None:
    p = parse_quantity("2 servings")
    assert p.value == 2.0
    assert p.is_count is True


def test_parse_bare_number() -> None:
    p = parse_quantity("3")
    assert p.value == 3.0
    assert p.is_count is True


def test_parse_empty_defaults_to_one_serving() -> None:
    p = parse_quantity("")
    assert p.value == 1.0
    assert p.is_count is True


def test_parse_unknown_unit_treated_as_count() -> None:
    p = parse_quantity("1 banana")
    assert p.is_count is True
    assert p.value == 1.0


def test_scale_branded_per_serving_grams() -> None:
    food = {
        "calories": 200,
        "protein_g": 10.0,
        "carbs_g": 25.0,
        "fat_g": 5.0,
        "serving_size": 100.0,
        "serving_size_unit": "g",
    }
    parsed = parse_quantity("150g")
    scaled, conf = scale_macros(food, parsed)
    assert scaled["calories"] == 300
    assert scaled["protein_g"] == 15.0
    assert conf == "high"


def test_scale_sr_food_per_100g_basis() -> None:
    food = {
        "calories": 165,
        "protein_g": 31.0,
        "carbs_g": 0.0,
        "fat_g": 3.6,
        "serving_size": None,
        "serving_size_unit": None,
    }
    parsed = parse_quantity("200g")
    scaled, conf = scale_macros(food, parsed)
    assert scaled["calories"] == 330
    assert scaled["protein_g"] == 62.0
    assert conf == "high"


def test_scale_count_food_with_count_quantity() -> None:
    food = {
        "calories": 250,
        "protein_g": 12.0,
        "carbs_g": 30.0,
        "fat_g": 9.0,
        "serving_size": 1.0,
        "serving_size_unit": "wrap",
    }
    parsed = parse_quantity("2 wraps")
    scaled, conf = scale_macros(food, parsed)
    assert scaled["calories"] == 500
    assert conf == "medium"


def test_scale_unknown_quantity_low_confidence() -> None:
    food = {
        "calories": 100,
        "protein_g": 5.0,
        "carbs_g": 10.0,
        "fat_g": 3.0,
        "serving_size": None,
        "serving_size_unit": None,
    }
    parsed = parse_quantity("1 serving")
    scaled, conf = scale_macros(food, parsed)
    assert scaled["calories"] == 100
    assert conf == "low"
