from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ExtractResult


class ExtractProvider(ABC):
    @abstractmethod
    def extract(self, urls: list[str]) -> list[ExtractResult]:
        """Extract content or raise an explicit provider error."""
