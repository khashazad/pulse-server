from uuid import UUID, uuid4

import pytest

from diet_tracker_server.models.entries import FoodEntryCreate, FoodEntryResponse


def test_food_entry_create_accepts_usda_only() -> None:
    from diet_tracker_server.models import FoodEntryCreate

    entry = FoodEntryCreate(
        display_name="eggs",
        quantity_text="2 eggs",
        usda_fdc_id=171287,
        usda_description="Egg",
        calories=140,
        protein_g=12,
        carbs_g=1,
        fat_g=10,
    )
    assert entry.usda_fdc_id == 171287
    assert entry.custom_food_id is None


def test_food_entry_create_accepts_custom_only() -> None:
    from diet_tracker_server.models import FoodEntryCreate

    cf_id = uuid4()
    entry = FoodEntryCreate(
        display_name="my wrap",
        quantity_text="1 wrap",
        custom_food_id=cf_id,
        calories=350,
        protein_g=20,
        carbs_g=30,
        fat_g=15,
    )
    assert entry.custom_food_id == cf_id
    assert entry.usda_fdc_id is None


def test_food_entry_create_rejects_both_sources() -> None:
    from diet_tracker_server.models import FoodEntryCreate

    with pytest.raises(Exception):
        FoodEntryCreate(
            display_name="x",
            quantity_text="1",
            usda_fdc_id=1,
            usda_description="x",
            custom_food_id=uuid4(),
            calories=0,
            protein_g=0,
            carbs_g=0,
            fat_g=0,
        )


def test_food_entry_create_rejects_neither_source() -> None:
    from diet_tracker_server.models import FoodEntryCreate

    with pytest.raises(Exception):
        FoodEntryCreate(
            display_name="x",
            quantity_text="1",
            calories=0,
            protein_g=0,
            carbs_g=0,
            fat_g=0,
        )


def test_food_entry_create_rejects_missing_usda_description() -> None:
    from diet_tracker_server.models import FoodEntryCreate

    with pytest.raises(Exception):
        FoodEntryCreate(
            display_name="x",
            quantity_text="1",
            usda_fdc_id=1,
            calories=0,
            protein_g=0,
            carbs_g=0,
            fat_g=0,
        )


def test_food_entry_create_defaults_meal_link_to_none() -> None:
    entry = FoodEntryCreate(
        display_name="oats",
        quantity_text="80 g",
        usda_fdc_id=173904,
        usda_description="Oats, raw",
        calories=320,
        protein_g=10,
        carbs_g=54,
        fat_g=6,
    )
    assert entry.meal_id is None
    assert entry.meal_name is None


def test_food_entry_create_accepts_meal_link() -> None:
    meal_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    entry = FoodEntryCreate(
        display_name="oats",
        quantity_text="80 g",
        usda_fdc_id=173904,
        usda_description="Oats, raw",
        calories=320,
        protein_g=10,
        carbs_g=54,
        fat_g=6,
        meal_id=meal_id,
        meal_name="Breakfast",
    )
    assert entry.meal_id == meal_id
    assert entry.meal_name == "Breakfast"


def test_food_entry_response_exposes_meal_link() -> None:
    fields = FoodEntryResponse.model_fields
    assert "meal_id" in fields
    assert "meal_name" in fields
