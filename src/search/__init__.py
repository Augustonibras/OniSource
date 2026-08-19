"""Search retrieval abstractions for OniSource Phase 0."""

from .models import SearchResult
from .provider import SearchProvider

__all__ = ["SearchProvider", "SearchResult"]
