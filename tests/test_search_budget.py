from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from research import dry_run_search_payload
from src.search.budget import (
    ADVANCED_SEARCH_CREDITS,
    BudgetExceededError,
    SearchBudget,
)


def _fixed_now(year: int, month: int):
    return lambda: datetime(year, month, 1, tzinfo=timezone.utc)


def test_advanced_search_costs_two_credits(tmp_path) -> None:
    state_path = tmp_path / "credit_usage.json"
    budget = SearchBudget(state_path, now_provider=_fixed_now(2026, 8))

    charged = budget.record_search(cache_hit=False)

    assert charged == ADVANCED_SEARCH_CREDITS == 2
    assert budget.execution_credits == 2
    assert budget.monthly_credits() == 2


def test_cache_hit_costs_zero_and_does_not_create_state(tmp_path) -> None:
    state_path = tmp_path / "credit_usage.json"
    budget = SearchBudget(state_path, now_provider=_fixed_now(2026, 8))

    charged = budget.record_search(cache_hit=True)

    assert charged == 0
    assert budget.execution_credits == 0
    assert not state_path.exists()


def test_execution_credit_limit_stops_before_extra_search(tmp_path) -> None:
    budget = SearchBudget(
        tmp_path / "credit_usage.json",
        now_provider=_fixed_now(2026, 8),
    )
    for _ in range(30):
        budget.record_search(cache_hit=False)

    with pytest.raises(BudgetExceededError, match="Execution credit limit"):
        budget.record_search(cache_hit=False)

    assert budget.execution_credits == 60
    assert budget.monthly_credits() == 60


def test_monthly_credit_limit_stops_before_search(tmp_path) -> None:
    state_path = tmp_path / "credit_usage.json"
    state_path.write_text(
        json.dumps({"month": "2026-08", "credits_used": 700}),
        encoding="utf-8",
    )
    budget = SearchBudget(state_path, now_provider=_fixed_now(2026, 8))

    with pytest.raises(BudgetExceededError, match="Monthly credit limit"):
        budget.record_search(cache_hit=False)

    assert budget.execution_credits == 0
    assert budget.monthly_credits() == 700


def test_monthly_usage_resets_when_month_changes(tmp_path) -> None:
    state_path = tmp_path / "credit_usage.json"
    state_path.write_text(
        json.dumps({"month": "2026-07", "credits_used": 698}),
        encoding="utf-8",
    )
    budget = SearchBudget(state_path, now_provider=_fixed_now(2026, 8))

    budget.record_search(cache_hit=False)

    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "month": "2026-08",
        "credits_used": 2,
    }


def test_dry_run_lists_queries_and_cost_without_creating_budget_state(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    payload = dry_run_search_payload("phosphoric acid")

    assert payload["dry_run"] is True
    assert payload["estimated_credits"] == len(payload["queries"]) * 2
    assert not (tmp_path / ".cache" / "credit_usage.json").exists()
