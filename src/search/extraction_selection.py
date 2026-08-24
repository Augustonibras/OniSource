from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from .domain_filter import SearchDomainFilter
from .marketplace import MarketplaceDomainRegistry
from .models import SearchResult


MAX_EXTRACTIONS_PER_CASE = 200


def attach_extraction_signals(
    results: Iterable[SearchResult],
    *,
    domain_filter: SearchDomainFilter | None = None,
    marketplace_registry: MarketplaceDomainRegistry | None = None,
) -> list[SearchResult]:
    """Attach human-configured hints without filtering any search result."""

    noise = domain_filter or SearchDomainFilter()
    marketplaces = marketplace_registry or MarketplaceDomainRegistry()
    annotated: list[SearchResult] = []
    for result in results:
        marketplace_reason = marketplaces.match_reason(result.url)
        noise_reason = noise.match_reason(result.url)
        annotated.append(
            replace(
                result,
                marketplace_signal=marketplace_reason is not None,
                marketplace_signal_reason=marketplace_reason or "",
                noise_signal=noise_reason is not None,
                noise_signal_reason=noise_reason or "",
            )
        )
    return annotated


def select_extraction_urls(
    results: Iterable[SearchResult],
    *,
    limit: int = MAX_EXTRACTIONS_PER_CASE,
) -> list[str]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("extraction URL limit must be a positive integer")
    if limit > MAX_EXTRACTIONS_PER_CASE:
        raise ValueError(
            f"extraction URL limit cannot exceed {MAX_EXTRACTIONS_PER_CASE}"
        )

    selected: list[str] = []
    seen: set[str] = set()
    for result in results:
        url = result.url
        if url in seen:
            continue
        seen.add(url)
        selected.append(url)
        if len(selected) == limit:
            break
    return selected
