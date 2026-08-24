from __future__ import annotations

from src.search.company_evaluation import build_company_classification_report
from src.search.extraction_selection import (
    MAX_EXTRACTIONS_PER_CASE,
    attach_extraction_signals,
    select_extraction_urls,
)
from src.search.marketplace import MarketplaceDomainRegistry, load_marketplace_domains
from src.search.models import SearchResult


def _result(url: str, title: str, content: str = "") -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        snippet="",
        content=content,
        raw_score=1.0,
        provider="cassette",
        query="phase zero query",
        retrieved_at="2026-08-20T12:00:00Z",
    )


def test_human_marketplace_configuration_is_loadable() -> None:
    domains = load_marketplace_domains()

    assert "alibaba.com" in domains
    assert "metoree.com" in domains
    assert "chemicalbook.com" in domains
    assert len(domains) == 18


def test_marketplace_registry_matches_subdomains() -> None:
    registry = MarketplaceDomainRegistry()

    assert registry.matches_url("https://www.alibaba.com/product")
    assert registry.matches_url("https://us.metoree.com/categories/6558")
    assert not registry.matches_url("https://www.tronox.com")


def test_marketplace_result_is_gated_and_excluded_from_role_counts() -> None:
    report = build_company_classification_report(
        "titanium_dioxide",
        [
            _result(
                "https://www.alibaba.com/product",
                "Tronox Titanium Dioxide Manufacturer, Alibaba",
                "Tronox is a titanium dioxide manufacturer.",
            ),
            _result(
                "https://www.tronox.com",
                "Tronox",
                "Tronox is a titanium dioxide manufacturer.",
            ),
        ],
    )

    rows = report["results"]
    assert rows[0]["domain_classification"]["role"] == "MARKETPLACE"
    assert rows[0]["domain_classification"]["reason_codes"] == [
        "MARKETPLACE_DOMAIN_HUMAN_CONFIG"
    ]
    assert report["role_distribution"]["total_results"] == 2
    assert report["role_distribution"]["marketplace_results"] == 1
    assert report["role_distribution"]["role_denominator"] == 1


def test_extraction_selection_keeps_gated_results_and_deduplicates_urls() -> None:
    results = [
        _result("https://www.alibaba.com/product", "Marketplace"),
        _result("https://wikipedia.org/wiki/test", "Noise"),
        _result("https://candidate.example/tds.pdf", "Candidate PDF"),
        _result("https://candidate.example/tds.pdf", "Duplicate PDF"),
        _result("https://second.example/product", "Second candidate"),
    ]

    annotated = attach_extraction_signals(results)
    selected = select_extraction_urls(annotated, limit=40)

    assert selected == [
        "https://www.alibaba.com/product",
        "https://wikipedia.org/wiki/test",
        "https://candidate.example/tds.pdf",
        "https://second.example/product",
    ]
    assert annotated[0].marketplace_signal is True
    assert annotated[0].marketplace_signal_reason == (
        "MARKETPLACE_DOMAIN:alibaba.com"
    )
    assert annotated[1].noise_signal is True
    assert annotated[1].noise_signal_reason == "EXCLUDE_DOMAIN:wikipedia.org"


def test_extraction_selection_enforces_two_hundred_url_limit() -> None:
    results = [
        _result(f"https://candidate-{index}.example/product", f"Candidate {index}")
        for index in range(205)
    ]

    selected = select_extraction_urls(results)

    assert MAX_EXTRACTIONS_PER_CASE == 200
    assert len(selected) == 200
    assert selected[0].endswith("candidate-0.example/product")
    assert selected[-1].endswith("candidate-199.example/product")
