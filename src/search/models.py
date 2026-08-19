from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    content: str
    raw_score: float
    provider: str
    query: str
    retrieved_at: str

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("SearchResult.url is required")
        if not self.provider.strip():
            raise ValueError("SearchResult.provider is required")
        if not self.query.strip():
            raise ValueError("SearchResult.query is required")

        try:
            parsed = datetime.fromisoformat(self.retrieved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("SearchResult.retrieved_at must be UTC ISO 8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("SearchResult.retrieved_at must be UTC ISO 8601")
