"""Unit tests for Pydantic model validators with branch-level edge cases.

Covers the storability validators that the request/response DTOs enforce:
``MacroTargets.target_weight_lb`` and ``WeightEntryUpsert.weight`` both reject
values that round below ``0.01`` or exceed the column's storable maximum.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pulse_server.models import MacroTargets
from pulse_server.models.weight import WeightEntryUpsert


def test_macro_targets_accepts_storable_weight() -> None:
    """A normal target weight is quantized to two decimals and kept."""
    t = MacroTargets(calories=2000, protein_g=150.0, carbs_g=200.0, fat_g=60.0, target_weight_lb=180.5)
    assert t.target_weight_lb == 180.5


def test_macro_targets_rejects_substorable_weight() -> None:
    """A target weight that rounds to <= 0 is rejected."""
    with pytest.raises(ValidationError):
        MacroTargets(
            calories=2000, protein_g=150.0, carbs_g=200.0, fat_g=60.0, target_weight_lb=0.001
        )


def test_weight_upsert_accepts_normal_value() -> None:
    """A normal weight passes the storability check."""
    w = WeightEntryUpsert(weight=Decimal("180.5"), unit="lb")
    assert w.weight == Decimal("180.5")


def test_weight_upsert_rejects_zero() -> None:
    """A weight that rounds to <= 0 is rejected."""
    with pytest.raises(ValidationError):
        WeightEntryUpsert(weight=Decimal("0.001"), unit="lb")


def test_weight_upsert_rejects_over_max() -> None:
    """A weight exceeding the per-unit storable maximum is rejected."""
    with pytest.raises(ValidationError):
        WeightEntryUpsert(weight=Decimal("99999"), unit="lb")
