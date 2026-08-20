from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class ExtractResult:
    url: str
    raw_content: str
    provider: str
    retrieved_at: str

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("ExtractResult.url is required")
        if not isinstance(self.raw_content, str):
            raise ValueError("ExtractResult.raw_content must be text")
        if not self.provider.strip():
            raise ValueError("ExtractResult.provider is required")
        try:
            parsed = datetime.fromisoformat(self.retrieved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("ExtractResult.retrieved_at must be UTC ISO 8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("ExtractResult.retrieved_at must be UTC ISO 8601")
