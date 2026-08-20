from __future__ import annotations

import pytest

from src.search.company_evaluation import build_company_classification_report
from src.search.models import SearchResult
from src.search.page_classification import PageType, classify_page


def _result(
    url: str,
    title: str,
    content: str,
) -> SearchResult:
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


@pytest.mark.parametrize(
    ("url", "content", "expected"),
    [
        (
            "https://example.test/report",
            "Market size, CAGR, forecast, and download sample.",
            PageType.MARKET_REPORT,
        ),
        (
            "https://example.test/trade-data",
            "Real-time shipment data from an importers/exporters database.",
            PageType.TRADE_DATA_PLATFORM,
        ),
        (
            "https://example.test/association",
            "The industry association represents its members.",
            PageType.ASSOCIATION,
        ),
        (
            "https://example.test/news",
            "Press release: Acme announces a plant expansion.",
            PageType.NEWS,
        ),
        (
            "https://example.test/company",
            "Acme product and company information.",
            PageType.COMPANY,
        ),
    ],
)
def test_page_type_is_assigned_before_commercial_role(
    url: str,
    content: str,
    expected: PageType,
) -> None:
    result = _result(url, content, content)

    classification = classify_page(result)
    assert classification.page_type is expected
    if expected is PageType.COMPANY:
        assert classification.evidence_excerpt == ""
    else:
        assert classification.evidence_excerpt
        assert classification.source_type == "COMBINED_PAGE_CONTENT"


def test_non_company_page_cannot_receive_commercial_role() -> None:
    report = build_company_classification_report(
        "unconfigured_category",
        [
            _result(
                "https://reports.example/market",
                "Acme manufacturer market report",
                "Acme is a manufacturer. Market size and CAGR forecast.",
            )
        ],
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["page_type"] == "MARKET_REPORT"
    assert classification["role"] == "NOT_A_COMPANY"
    assert report["role_distribution"]["non_company_results"] == 1
    assert report["role_distribution"]["role_denominator"] == 0


def test_manufacturer_claim_without_positive_production_signal_is_unknown() -> None:
    report = build_company_classification_report(
        "unconfigured_category",
        [
            _result(
                "https://acme.example/product",
                "Acme product",
                "Acme is a manufacturer of this product.",
            )
        ],
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["role"] == "UNKNOWN"
    assert classification["reason_codes"] == [
        "MANUFACTURER_POSITIVE_PRODUCTION_SIGNAL_REQUIRED"
    ]


@pytest.mark.parametrize(
    "production_signal",
    [
        "Our installed capacity is 100,000 tonnes/year.",
        "We use the chloride process for production.",
        "Our manufacturing plant is located in Bahia.",
        "We have 25 years of manufacturing experience.",
    ],
)
def test_positive_production_signal_allows_probable_manufacturer(
    production_signal: str,
) -> None:
    report = build_company_classification_report(
        "unconfigured_category",
        [
            _result(
                "https://acme.example/product",
                "Acme product",
                f"Acme is a manufacturer. {production_signal}",
            )
        ],
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["role"] == "MANUFACTURER"
    assert classification["detailed_classification"] == "PROBABLE_MANUFACTURER"


def test_broad_unrelated_chemical_catalog_downgrades_to_trader() -> None:
    report = build_company_classification_report(
        "titanium_dioxide",
        [
            _result(
                "https://acme.example/titanium-dioxide",
                "Acme titanium dioxide",
                (
                    "Acme is a manufacturer with 25 years of manufacturing. "
                    "Our product catalog includes solvents, resins, detergents, "
                    "water treatment chemicals, and plasticizers."
                ),
            )
        ],
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["role"] == "TRADER"
    assert classification["reason_codes"] == [
        "BROAD_UNRELATED_CHEMICAL_CATALOG_AUTOMATIC_TRADER"
    ]


def test_third_party_brand_sale_downgrades_to_trader() -> None:
    report = build_company_classification_report(
        "titanium_dioxide",
        [
            _result(
                "https://seller.example/r996",
                "BILLIONS R996 supplier",
                (
                    "Seller is a manufacturer with 25 years of manufacturing. "
                    "Buy BILLIONS R996 product wholesale."
                ),
            )
        ],
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["role"] == "TRADER"
    assert classification["reason_codes"] == [
        "THIRD_PARTY_BRAND_SALE_AUTOMATIC_TRADER"
    ]


def test_brand_holder_like_domain_still_requires_production_evidence() -> None:
    report = build_company_classification_report(
        "titanium_dioxide",
        [
            _result(
                "https://lomonbillions.global/product",
                "BILLIONS product",
                (
                    "Lomon Billions is a manufacturer with 35 years of "
                    "manufacturing experience."
                ),
            )
        ],
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["role"] == "MANUFACTURER"
    assert "THIRD_PARTY_BRAND_SALE_AUTOMATIC_TRADER" not in classification[
        "reason_codes"
    ]
