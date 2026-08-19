from __future__ import annotations

from abc import ABC, abstractmethod

from .models import SearchResult


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Return normalized results or raise an explicit provider error."""
