from __future__ import annotations

from collections.abc import Iterable

from .domain_filter import SearchDomainFilter
from .marketplace import MarketplaceDomainRegistry
from .models import SearchResult


MAX_EXTRACTION_URLS_PER_CASE = 40


def select_extraction_urls(
    results: Iterable[SearchResult],
    *,
    limit: int = MAX_EXTRACTION_URLS_PER_CASE,
    domain_filter: SearchDomainFilter | None = None,
    marketplace_registry: MarketplaceDomainRegistry | None = None,
) -> list[str]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("extraction URL limit must be a positive integer")
    if limit > MAX_EXTRACTION_URLS_PER_CASE:
        raise ValueError(
            f"extraction URL limit cannot exceed {MAX_EXTRACTION_URLS_PER_CASE}"
        )

    noise = domain_filter or SearchDomainFilter()
    marketplaces = marketplace_registry or MarketplaceDomainRegistry()
    selected: list[str] = []
    seen: set[str] = set()
    for result in results:
        url = result.url
        if url in seen:
            continue
        seen.add(url)
        if noise.excludes_url(url) or marketplaces.matches_url(url):
            continue
        selected.append(url)
        if len(selected) == limit:
            break
    return selected
