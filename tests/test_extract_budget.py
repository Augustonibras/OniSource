from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.extract.budget import EXTRACT_EXECUTION_CREDIT_LIMIT, ExtractBudget
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
    budget = ExtractBudget(
        state_path,
        now_provider=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(BudgetExceededError):
        budget.ensure_batch_available(20)


def test_extract_budget_has_an_independent_eighty_credit_execution_cap(
    tmp_path,
) -> None:
    budget = ExtractBudget(tmp_path / "credits.json")

    for _ in range(20):
        budget.record_extraction(20)

    assert EXTRACT_EXECUTION_CREDIT_LIMIT == 80
    assert budget.execution_credits == 80
    with pytest.raises(BudgetExceededError, match="limit of 80"):
        budget.ensure_batch_available(1)
