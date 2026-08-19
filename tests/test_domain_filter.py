from __future__ import annotations

from src.search.domain_filter import SearchDomainFilter


def test_noise_and_local_suffix_domains_are_excluded() -> None:
    domain_filter = SearchDomainFilter()
    raw_results = [
        {"url": "https://en.wikipedia.org/wiki/Titanium_dioxide"},
        {"url": "https://chemistry.example.edu/reference"},
        {"url": "https://university.edu.br/paper"},
        {"url": "https://agency.gov/document"},
        {"url": "https://manufacturer.example/product"},
    ]

    filtered = domain_filter.filter_raw_results(raw_results)

    assert filtered == [{"url": "https://manufacturer.example/product"}]


def test_pdf_result_on_allowed_domain_is_preserved() -> None:
    domain_filter = SearchDomainFilter()
    pdf_result = {
        "url": "https://manufacturer.example/documents/product-tds.pdf"
    }

    filtered = domain_filter.filter_raw_results([pdf_result])

    assert filtered == [pdf_result]


def test_market_report_and_directory_noise_domains_are_excluded() -> None:
    domain_filter = SearchDomainFilter()
    raw_results = [
        {"url": "https://www.mordorintelligence.com/report"},
        {"url": "https://marketsandmarkets.com/market-report"},
        {"url": "https://camaphosphoricacid.com/ranking"},
        {"url": "https://www.databridgemarketresearch.com/reports/example"},
    ]

    assert domain_filter.filter_raw_results(raw_results) == []
