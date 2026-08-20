from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from src.extract.audit import freeze_extract_cache_as_cassette
from src.extract.budget import ExtractBudget
from src.extract.cache import CachedExtractProvider
from src.extract.cassette import (
    DEFAULT_EXTRACT_CASSETTE_DIR,
    CassetteExtractProvider,
)
from src.extract.models import ExtractResult
from src.extract.provider import ExtractProvider
from src.extract.tavily import TavilyExtractProvider
from src.search.audit import freeze_cache_as_cassette, freeze_run_as_cassette
from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.cassette import CassetteSearchProvider
from src.search.company_evaluation import build_company_classification_report
from src.search.coverage import build_ground_truth_coverage
from src.search.extraction_selection import select_extraction_urls
from src.search.models import SearchResult
from src.search.provider import SearchProvider
from src.search.query_builder import QUERY_SET_VERSION, build_search_queries
from src.search.tavily import TavilySearchProvider
from src.simple_yaml import load_yaml_mapping


PROJECT_ROOT = Path(__file__).resolve().parent
CATEGORY_PATHS = {
    "titanium_dioxide": PROJECT_ROOT / "config" / "categories" / "titanium_dioxide.yaml",
    "phosphoric_acid": PROJECT_ROOT / "config" / "categories" / "phosphoric_acid.yaml",
}
PHASE_ZERO_CASES = (
    {
        "case": "A",
        "product_name": "BILLIONS R996 Titanium Dioxide",
        "category": "titanium_dioxide",
    },
    {
        "case": "B",
        "product_name": "Phosphoric Acid",
        "category": "phosphoric_acid",
    },
)


def load_category(name: str) -> dict[str, Any]:
    return load_yaml_mapping(CATEGORY_PATHS[name])


def load_search_category_config(category: str | None) -> dict[str, Any] | None:
    if not category:
        return None
    normalized_key = "_".join(category.casefold().replace("_", " ").split())
    if normalized_key not in CATEGORY_PATHS:
        return None
    return load_category(normalized_key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OniSource Phase 0 local foundation")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show implemented and deferred capabilities")
    category_parser = subparsers.add_parser("show-category", help="Show category rules")
    category_parser.add_argument("category", choices=sorted(CATEGORY_PATHS))
    search_parser = subparsers.add_parser("search", help="Prepare a search execution")
    search_parser.add_argument("product_name")
    search_parser.add_argument("--category")
    search_parser.add_argument("--dry-run", action="store_true")
    search_parser.add_argument(
        "--live",
        action="store_true",
        help="Call Tavily explicitly instead of replaying committed cassettes",
    )
    search_parser.add_argument(
        "--refresh-cassettes",
        action="store_true",
        help="Deliberately replace cassettes after an explicit live search",
    )
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Run both Phase 0 cases offline against committed cassettes",
    )
    benchmark_parser.add_argument(
        "--live",
        action="store_true",
        help="Call Tavily explicitly instead of replaying committed cassettes",
    )
    benchmark_parser.add_argument(
        "--refresh-cassettes",
        action="store_true",
        help="Deliberately replace all Phase 0 cassettes during a live run",
    )
    benchmark_parser.add_argument(
        "--live-extract",
        action="store_true",
        help="Call Tavily Extract while replaying search cassettes offline",
    )
    benchmark_parser.add_argument(
        "--refresh-extract-cassettes",
        action="store_true",
        help="Deliberately replace Phase 0 extraction cassettes",
    )
    cassette_parser = subparsers.add_parser(
        "freeze-cassette", help="Freeze a reviewed live response"
    )
    cassette_parser.add_argument("run_response")
    cassette_parser.add_argument("--refresh-cassettes", action="store_true")
    return parser


def status_payload() -> dict[str, Any]:
    return {
        "project": "OniSource",
        "phase": 0,
        "interface": "CLI",
        "implemented": [
            "structured_models",
            "evidence_contract",
            "company_classification",
            "document_classification",
            "technical_matching_foundation",
            "specification_compliance",
            "pipeline_metrics",
            "search_provider",
            "search_query_builder",
            "search_budget_guard",
            "offline_benchmark",
            "evidence_based_company_evaluation",
            "extract_provider",
        ],
        "deferred": ["llm"],
    }


def dry_run_search_payload(
    product_name: str,
    category: str | None = None,
) -> dict[str, Any]:
    queries = build_search_queries(
        product_name,
        category,
        category_config=load_search_category_config(category),
    )
    return {
        "dry_run": True,
        "queries": queries,
        "estimated_credits": SearchBudget.estimate_credits(len(queries)),
    }


def live_search_payload(
    product_name: str,
    category: str | None = None,
    *,
    refresh_cassettes: bool = False,
) -> dict[str, Any]:
    queries = build_search_queries(
        product_name,
        category,
        category_config=load_search_category_config(category),
    )
    budget = SearchBudget()
    live_provider = TavilySearchProvider(budget=budget)
    provider = CachedSearchProvider(
        live_provider,
        provider_name=live_provider.provider_name,
        depth=live_provider.search_depth,
        request_parameters=live_provider.request_parameters,
        refresh=refresh_cassettes,
    )
    after_query = (
        _cassette_refresh_callback(provider)
        if refresh_cassettes
        else None
    )
    query_results, all_results = _execute_queries(
        provider,
        queries,
        after_query=after_query,
    )
    payload: dict[str, Any] = {
        "provider_mode": "live",
        "dry_run": False,
        "queries": query_results,
        "execution_credits": budget.execution_credits,
        "monthly_credits": budget.monthly_credits(),
        "company_classification": build_company_classification_report(
            category or "",
            all_results,
        ),
    }
    coverage = build_ground_truth_coverage(category or "", all_results)
    if coverage is not None:
        payload["coverage"] = coverage
    return payload


def cassette_search_payload(
    product_name: str,
    category: str | None = None,
) -> dict[str, Any]:
    queries = build_search_queries(
        product_name,
        category,
        category_config=load_search_category_config(category),
    )
    provider = CassetteSearchProvider()
    query_results, all_results = _execute_queries(provider, queries)
    payload: dict[str, Any] = {
        "provider_mode": "cassette",
        "dry_run": False,
        "queries": query_results,
        "execution_credits": 0,
        "company_classification": build_company_classification_report(
            category or "",
            all_results,
        ),
    }
    coverage = build_ground_truth_coverage(category or "", all_results)
    if coverage is not None:
        payload["coverage"] = coverage
    return payload


def _execute_queries(
    provider: SearchProvider,
    queries: list[str],
    *,
    after_query: Callable[[str, int], None] | None = None,
) -> tuple[list[dict[str, object]], list[SearchResult]]:
    query_results: list[dict[str, object]] = []
    all_results: list[SearchResult] = []
    for query in queries:
        results = provider.search(query)
        if after_query is not None:
            after_query(query, 10)
        all_results.extend(results)
        query_results.append(
            {
                "query": query,
                "results": [asdict(result) for result in results],
            }
        )
    return query_results, all_results


def _cassette_refresh_callback(
    provider: CachedSearchProvider,
) -> Callable[[str, int], None]:
    def freeze(query: str, max_results: int) -> None:
        freeze_cache_as_cassette(
            provider.cache_path(query, max_results),
            refresh_cassettes=True,
        )

    return freeze


def _group_domains_and_titles(
    results: list[SearchResult],
) -> dict[str, list[str]]:
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for result in results:
        domain = (urlsplit(result.url).hostname or "UNKNOWN_DOMAIN").casefold()
        title_key = " ".join(result.title.split()).casefold()
        grouped[domain].setdefault(title_key, result.title)
    return {
        domain: sorted(titles.values(), key=str.casefold)
        for domain, titles in sorted(grouped.items())
    }


def _extract_batches(urls: list[str], batch_size: int = 20) -> list[list[str]]:
    return [urls[index : index + batch_size] for index in range(0, len(urls), batch_size)]


def _extract_case_content(
    results: list[SearchResult],
    provider: ExtractProvider | None,
    *,
    provider_mode: str,
    budget: ExtractBudget | None = None,
    refresh_cassettes: bool = False,
) -> tuple[dict[str, str], dict[str, object]]:
    selected_urls = select_extraction_urls(results)
    if provider is None:
        return {}, {
            "provider_mode": "NOT_AVAILABLE",
            "url_limit": 40,
            "candidate_urls": len(selected_urls),
            "attempted_urls": 0,
            "successful_urls": 0,
            "failed_urls": 0,
            "batches": 0,
            "cache_hits": 0,
            "credits_consumed": 0,
        }

    credits_before = budget.execution_credits if budget is not None else 0
    extracted: dict[str, str] = {}
    batches = _extract_batches(selected_urls)
    cache_hits = 0
    for batch in batches:
        batch_results: list[ExtractResult] = provider.extract(batch)
        if isinstance(provider, CachedExtractProvider):
            cache_hits += int(provider.last_cache_hit)
            if refresh_cassettes:
                freeze_extract_cache_as_cassette(
                    provider.cache_path(batch),
                    refresh_cassettes=True,
                )
        for item in batch_results:
            extracted[item.url] = item.raw_content

    return extracted, {
        "provider_mode": provider_mode,
        "url_limit": 40,
        "candidate_urls": len(selected_urls),
        "attempted_urls": len(selected_urls),
        "successful_urls": len(extracted),
        "failed_urls": len(selected_urls) - len(extracted),
        "batches": len(batches),
        "cache_hits": cache_hits,
        "credits_consumed": (
            budget.execution_credits - credits_before if budget is not None else 0
        ),
    }


def benchmark_payload(
    *,
    live: bool = False,
    refresh_cassettes: bool = False,
    live_extract: bool = False,
    refresh_extract_cassettes: bool = False,
    extract_cassette_dir: str | Path = DEFAULT_EXTRACT_CASSETTE_DIR,
) -> dict[str, Any]:
    if refresh_cassettes and not live:
        raise ValueError("refresh_cassettes requires live=True")
    if refresh_extract_cassettes and not live_extract:
        raise ValueError("refresh_extract_cassettes requires live_extract=True")
    if live and live_extract:
        raise ValueError("search live and extract live cannot run together")
    budget = SearchBudget() if live else None
    if live:
        live_provider = TavilySearchProvider(budget=budget)
        provider: SearchProvider = CachedSearchProvider(
            live_provider,
            provider_name=live_provider.provider_name,
            depth=live_provider.search_depth,
            request_parameters=live_provider.request_parameters,
            refresh=refresh_cassettes,
        )
    else:
        provider = CassetteSearchProvider()

    extract_budget = ExtractBudget() if live_extract else None
    extract_path = Path(extract_cassette_dir)
    if live_extract:
        live_extract_provider = TavilyExtractProvider(budget=extract_budget)
        extract_provider: ExtractProvider | None = CachedExtractProvider(
            live_extract_provider,
            provider_name=live_extract_provider.provider_name,
            depth=live_extract_provider.extract_depth,
            request_parameters=live_extract_provider.request_parameters,
            refresh=refresh_extract_cassettes,
        )
        extract_provider_mode = "live"
    elif extract_path.is_dir() and any(extract_path.glob("*.json")):
        extract_provider = CassetteExtractProvider(extract_path)
        extract_provider_mode = "cassette"
    else:
        extract_provider = None
        extract_provider_mode = "NOT_AVAILABLE"

    case_payloads = []
    for case in PHASE_ZERO_CASES:
        category = case["category"]
        queries = build_search_queries(
            case["product_name"],
            category,
            category_config=load_search_category_config(category),
        )
        credits_before = budget.execution_credits if budget is not None else 0
        after_query = (
            _cassette_refresh_callback(provider)
            if refresh_cassettes and isinstance(provider, CachedSearchProvider)
            else None
        )
        _, results = _execute_queries(
            provider,
            queries,
            after_query=after_query,
        )
        extracted_content, extraction = _extract_case_content(
            results,
            extract_provider,
            provider_mode=extract_provider_mode,
            budget=extract_budget,
            refresh_cassettes=refresh_extract_cassettes,
        )
        coverage = build_ground_truth_coverage(category, results)
        case_payloads.append(
            {
                "case": case["case"],
                "category": category,
                "query_count": len(queries),
                "credits_consumed": (
                    budget.execution_credits - credits_before
                    if budget is not None
                    else 0
                ),
                "retries": 0,
                "errors_by_type": {},
                "domains": _group_domains_and_titles(results),
                "coverage": coverage,
                "company_classification": build_company_classification_report(
                    category,
                    results,
                    extracted_content_by_url=extracted_content,
                ),
                "extraction": extraction,
            }
        )

    payload: dict[str, Any] = {
        "benchmark": "OniSource Phase 0",
        "provider_mode": "live" if live else "cassette",
        "extract_provider_mode": extract_provider_mode,
        "query_set_version": QUERY_SET_VERSION,
        "cases": case_payloads,
        "total_search_credits_consumed": (
            budget.execution_credits if budget is not None else 0
        ),
        "total_extraction_credits_consumed": (
            extract_budget.execution_credits if extract_budget is not None else 0
        ),
        "total_credits_consumed": (
            (budget.execution_credits if budget is not None else 0)
            + (extract_budget.execution_credits if extract_budget is not None else 0)
        ),
    }
    if budget is not None:
        payload["monthly_credits"] = budget.monthly_credits()
    if extract_budget is not None:
        payload["monthly_credits"] = extract_budget.monthly_credits()
    return payload


def main(argv: list[str] | None = None) -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {None, "status"}:
        payload = status_payload()
    elif args.command == "search":
        if args.dry_run and args.live:
            parser.error("--dry-run and --live cannot be used together")
        if args.refresh_cassettes and not args.live:
            parser.error("--refresh-cassettes requires --live")
        if args.dry_run:
            payload = dry_run_search_payload(args.product_name, args.category)
        elif args.live:
            payload = live_search_payload(
                args.product_name,
                args.category,
                refresh_cassettes=args.refresh_cassettes,
            )
        else:
            payload = cassette_search_payload(args.product_name, args.category)
    elif args.command == "benchmark":
        if args.refresh_cassettes and not args.live:
            parser.error("--refresh-cassettes requires --live")
        if args.refresh_extract_cassettes and not args.live_extract:
            parser.error("--refresh-extract-cassettes requires --live-extract")
        if args.live and args.live_extract:
            parser.error("--live and --live-extract cannot be combined")
        payload = benchmark_payload(
            live=args.live,
            refresh_cassettes=args.refresh_cassettes,
            live_extract=args.live_extract,
            refresh_extract_cassettes=args.refresh_extract_cassettes,
        )
    elif args.command == "freeze-cassette":
        cassette_path = freeze_run_as_cassette(
            args.run_response,
            refresh_cassettes=args.refresh_cassettes,
        )
        payload = {"cassette": str(cassette_path), "frozen": True}
    else:
        payload = load_category(args.category)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
