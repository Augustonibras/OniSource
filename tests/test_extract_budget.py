from __future__ import annotations

import json

import pytest

from src.extract.budget import ExtractBudget
from src.search.budget import BudgetExceededError


@pytest.mark.parametrize(
    ("successful_urls", "expected_credits"),
    [(0, 0), (1, 1), (5, 1), (6, 2), (20, 4)],
)
def test_basic_extract_costs_one_credit_per_five_successes(
    tmp_path,
    successful_urls: int,
    expected_credits: int,
) -> None:
    budget = ExtractBudget(tmp_path / f"credits-{successful_urls}.json")

    charged = budget.record_extraction(successful_urls)

    assert charged == expected_credits
    assert budget.execution_credits == expected_credits


def test_extract_budget_preflight_stops_before_network_limit(tmp_path) -> None:
    state_path = tmp_path / "credits.json"
    state_path.write_text(
        json.dumps({"month": "2026-08", "credits_used": 699}),
        encoding="utf-8",
    )
    budget = ExtractBudget(state_path)

    with pytest.raises(BudgetExceededError):
        budget.ensure_batch_available(20)
