from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.search.audit import freeze_run_as_cassette
from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.cassette import CassetteSearchProvider
from src.search.coverage import build_ground_truth_coverage
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
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Run both Phase 0 cases offline against committed cassettes",
    )
    benchmark_parser.add_argument(
        "--live",
        action="store_true",
        help="Call Tavily explicitly instead of replaying committed cassettes",
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
    )
    query_results, all_results = _execute_queries(provider, queries)
    payload: dict[str, Any] = {
        "provider_mode": "live",
        "dry_run": False,
        "queries": query_results,
        "execution_credits": budget.execution_credits,
        "monthly_credits": budget.monthly_credits(),
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
    }
    coverage = build_ground_truth_coverage(category or "", all_results)
    if coverage is not None:
        payload["coverage"] = coverage
    return payload


def _execute_queries(
    provider: SearchProvider,
    queries: list[str],
) -> tuple[list[dict[str, object]], list[SearchResult]]:
    query_results: list[dict[str, object]] = []
    all_results: list[SearchResult] = []
    for query in queries:
        results = provider.search(query)
        all_results.extend(results)
        query_results.append(
            {
                "query": query,
                "results": [asdict(result) for result in results],
            }
        )
    return query_results, all_results


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


def benchmark_payload(*, live: bool = False) -> dict[str, Any]:
    budget = SearchBudget() if live else None
    if live:
        live_provider = TavilySearchProvider(budget=budget)
        provider: SearchProvider = CachedSearchProvider(
            live_provider,
            provider_name=live_provider.provider_name,
            depth=live_provider.search_depth,
        )
    else:
        provider = CassetteSearchProvider()

    case_payloads = []
    for case in PHASE_ZERO_CASES:
        category = case["category"]
        queries = build_search_queries(
            case["product_name"],
            category,
            category_config=load_search_category_config(category),
        )
        credits_before = budget.execution_credits if budget is not None else 0
        _, results = _execute_queries(provider, queries)
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
            }
        )

    payload: dict[str, Any] = {
        "benchmark": "OniSource Phase 0",
        "provider_mode": "live" if live else "cassette",
        "query_set_version": QUERY_SET_VERSION,
        "cases": case_payloads,
        "total_credits_consumed": budget.execution_credits if budget is not None else 0,
    }
    if budget is not None:
        payload["monthly_credits"] = budget.monthly_credits()
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
        if args.dry_run:
            payload = dry_run_search_payload(args.product_name, args.category)
        elif args.live:
            payload = live_search_payload(args.product_name, args.category)
        else:
            payload = cassette_search_payload(args.product_name, args.category)
    elif args.command == "benchmark":
        payload = benchmark_payload(live=args.live)
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
