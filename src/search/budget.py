from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ADVANCED_SEARCH_CREDITS = 2
EXECUTION_CREDIT_LIMIT = 60
MONTHLY_CREDIT_LIMIT = 700
DEFAULT_CREDIT_STATE_PATH = Path(".cache") / "credit_usage.json"


class BudgetExceededError(RuntimeError):
    """Raised before a search that would exceed an execution or monthly cap."""


class CreditUsageStateError(ValueError):
    """Raised when persisted credit state cannot be read deterministically."""


class SearchBudget:
    def __init__(
        self,
        state_path: str | Path = DEFAULT_CREDIT_STATE_PATH,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._execution_credits = 0

    @property
    def execution_credits(self) -> int:
        return self._execution_credits

    @staticmethod
    def estimate_credits(query_count: int, *, cache_hits: int = 0) -> int:
        if query_count < 0 or cache_hits < 0 or cache_hits > query_count:
            raise ValueError("query_count and cache_hits are inconsistent")
        return (query_count - cache_hits) * ADVANCED_SEARCH_CREDITS

    def record_search(self, *, cache_hit: bool) -> int:
        if cache_hit:
            return 0

        current_month = self._current_month()
        persisted_month, monthly_credits = self._load_monthly_state(current_month)
        projected_execution = self._execution_credits + ADVANCED_SEARCH_CREDITS
        projected_monthly = monthly_credits + ADVANCED_SEARCH_CREDITS

        if projected_execution > EXECUTION_CREDIT_LIMIT:
            raise BudgetExceededError(
                f"Execution credit limit of {EXECUTION_CREDIT_LIMIT} would be exceeded"
            )
        if projected_monthly > MONTHLY_CREDIT_LIMIT:
            raise BudgetExceededError(
                f"Monthly credit limit of {MONTHLY_CREDIT_LIMIT} would be exceeded"
            )

        self._write_monthly_state(persisted_month, projected_monthly)
        self._execution_credits = projected_execution
        return ADVANCED_SEARCH_CREDITS

    def monthly_credits(self) -> int:
        _, credits = self._load_monthly_state(self._current_month())
        return credits

    def _current_month(self) -> str:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        return now.astimezone(timezone.utc).strftime("%Y-%m")

    def _load_monthly_state(self, current_month: str) -> tuple[str, int]:
        if not self.state_path.exists():
            return current_month, 0
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CreditUsageStateError(
                f"Could not read credit usage state: {self.state_path}"
            ) from error

        if not isinstance(payload, dict):
            raise CreditUsageStateError("Credit usage state must be a JSON object")
        month = payload.get("month")
        credits = payload.get("credits_used")
        if not isinstance(month, str) or isinstance(credits, bool) or not isinstance(credits, int):
            raise CreditUsageStateError("Credit usage state has invalid fields")
        if credits < 0:
            raise CreditUsageStateError("Credit usage cannot be negative")
        if month != current_month:
            return current_month, 0
        return month, credits

    def _write_monthly_state(self, month: str, credits_used: int) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        payload = {"month": month, "credits_used": credits_used}
        try:
            temporary_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.state_path)
        except OSError as error:
            raise CreditUsageStateError(
                f"Could not write credit usage state: {self.state_path}"
            ) from error
