from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from .models import SearchResult


class PageType(str, Enum):
    COMPANY = "COMPANY"
    MARKET_REPORT = "MARKET_REPORT"
    NEWS = "NEWS"
    ASSOCIATION = "ASSOCIATION"
    TRADE_DATA_PLATFORM = "TRADE_DATA_PLATFORM"


@dataclass(frozen=True, slots=True)
class PageClassification:
    page_type: PageType
    reason_codes: tuple[str, ...]
    evidence_excerpt: str = ""
    source_type: str = ""


_MARKET_REPORT_PATTERNS = (
    re.compile(r"\bmarket\s+size\b", re.IGNORECASE),
    re.compile(r"\bcagr\b", re.IGNORECASE),
    re.compile(r"\bforecast\b", re.IGNORECASE),
    re.compile(r"\bdownload\s+(?:a\s+)?sample\b", re.IGNORECASE),
    re.compile(
        r"\breport\b.{0,80}\b20\d{2}\s*[-–—]\s*20\d{2}\b|"
        r"\b20\d{2}\s*[-–—]\s*20\d{2}\b.{0,80}\breport\b",
        re.IGNORECASE | re.DOTALL,
    ),
)
_TRADE_DATA_PATTERNS = (
    re.compile(r"\bshipment\s+data\b", re.IGNORECASE),
    re.compile(r"\bshipment\s+details?\b", re.IGNORECASE),
    re.compile(r"\breal[-\s]+time\s+shipments?\b", re.IGNORECASE),
    re.compile(
        r"\bforeign\s+trade\b.{0,80}\bimports?\b.{0,40}\bexports?\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\binternational\s+trade\s+transaction\s+data\b|"
        r"\bimport\s+and\s+export\s+records\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:importers?|exporters?)\s*(?:/|&|and)\s*"
        r"(?:importers?|exporters?)\s+database\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:importers?|exporters?)\b.{0,50}\bdatabase\b|"
        r"\bdatabase\b.{0,50}\b(?:importers?|exporters?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
)
_NEWS_PATTERN = re.compile(
    r"\bpress\s+release\b|\b(?:announces?|announced)\b.{0,100}"
    r"\b(?:ruling|agreement|launch|acquisition|expansion|investment)\b",
    re.IGNORECASE | re.DOTALL,
)
_ASSOCIATION_AND_MEMBERS_PATTERN = re.compile(
    r"\bassociation\b.{0,240}\bmembers?\b|"
    r"\bmembers?\b.{0,240}\bassociation\b",
    re.IGNORECASE | re.DOTALL,
)


def classify_page(
    result: SearchResult,
    *,
    extracted_content: str = "",
) -> PageClassification:
    """Classify page purpose before any commercial company-role decision."""

    text = "\n".join(
        value
        for value in (
            result.title,
            result.snippet,
            result.content,
            extracted_content,
        )
        if value
    )
    if any(pattern.search(text) for pattern in _MARKET_REPORT_PATTERNS):
        match = next(
            pattern.search(text)
            for pattern in _MARKET_REPORT_PATTERNS
            if pattern.search(text) is not None
        )
        assert match is not None
        return PageClassification(
            PageType.MARKET_REPORT,
            ("PAGE_SIGNALS_MARKET_REPORT",),
            text[max(0, match.start() - 80) : match.end() + 160].strip(),
            "COMBINED_PAGE_CONTENT",
        )
    if any(pattern.search(text) for pattern in _TRADE_DATA_PATTERNS):
        match = next(
            pattern.search(text)
            for pattern in _TRADE_DATA_PATTERNS
            if pattern.search(text) is not None
        )
        assert match is not None
        return PageClassification(
            PageType.TRADE_DATA_PLATFORM,
            ("PAGE_SIGNALS_TRADE_DATA_PLATFORM",),
            text[max(0, match.start() - 80) : match.end() + 160].strip(),
            "COMBINED_PAGE_CONTENT",
        )
    if (
        re.search(r"\bassociation\b", result.title, re.IGNORECASE)
        and _ASSOCIATION_AND_MEMBERS_PATTERN.search(text)
    ):
        match = _ASSOCIATION_AND_MEMBERS_PATTERN.search(text)
        assert match is not None
        return PageClassification(
            PageType.ASSOCIATION,
            ("PAGE_SIGNALS_ASSOCIATION_AND_MEMBERS",),
            text[max(0, match.start() - 80) : match.end() + 160].strip(),
            "COMBINED_PAGE_CONTENT",
        )
    if _NEWS_PATTERN.search(text):
        match = _NEWS_PATTERN.search(text)
        assert match is not None
        return PageClassification(
            PageType.NEWS,
            ("PAGE_SIGNALS_NEWS_EVENT",),
            text[max(0, match.start() - 80) : match.end() + 160].strip(),
            "COMBINED_PAGE_CONTENT",
        )
    return PageClassification(PageType.COMPANY, ("PAGE_DEFAULT_COMPANY",))


def marketplace_page_classification(result: SearchResult) -> PageClassification:
    """Map an existing human marketplace-domain gate into the page-type layer."""

    if not urlsplit(result.url).hostname:
        raise ValueError("marketplace result URL must contain a domain")
    return PageClassification(
        PageType.TRADE_DATA_PLATFORM,
        ("MARKETPLACE_DOMAIN_HUMAN_CONFIG",),
    )
