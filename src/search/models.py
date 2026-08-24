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
    marketplace_signal: bool = False
    marketplace_signal_reason: str = ""
    noise_signal: bool = False
    noise_signal_reason: str = ""

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("SearchResult.url is required")
        if not self.provider.strip():
            raise ValueError("SearchResult.provider is required")
        if not self.query.strip():
            raise ValueError("SearchResult.query is required")
        if not isinstance(self.marketplace_signal, bool):
            raise TypeError("SearchResult.marketplace_signal must be boolean")
        if not isinstance(self.marketplace_signal_reason, str):
            raise TypeError("SearchResult.marketplace_signal_reason must be text")
        if not isinstance(self.noise_signal, bool):
            raise TypeError("SearchResult.noise_signal must be boolean")
        if not isinstance(self.noise_signal_reason, str):
            raise TypeError("SearchResult.noise_signal_reason must be text")

        try:
            parsed = datetime.fromisoformat(self.retrieved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("SearchResult.retrieved_at must be UTC ISO 8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("SearchResult.retrieved_at must be UTC ISO 8601")
