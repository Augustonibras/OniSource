from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.search.audit import freeze_run_as_cassette
from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.coverage import build_ground_truth_coverage
from src.search.query_builder import build_search_queries
from src.search.tavily import TavilySearchProvider
from src.simple_yaml import load_yaml_mapping


PROJECT_ROOT = Path(__file__).resolve().parent
CATEGORY_PATHS = {
    "titanium_dioxide": PROJECT_ROOT / "config" / "categories" / "titanium_dioxide.yaml",
    "phosphoric_acid": PROJECT_ROOT / "config" / "categories" / "phosphoric_acid.yaml",
}


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
    all_results = []
    query_results = []
    for query in queries:
        results = provider.search(query)
        all_results.extend(results)
        query_results.append(
            {
                "query": query,
                "results": [asdict(result) for result in results],
            }
        )
    payload: dict[str, Any] = {
        "dry_run": False,
        "queries": query_results,
        "execution_credits": budget.execution_credits,
        "monthly_credits": budget.monthly_credits(),
    }
    coverage = build_ground_truth_coverage(category or "", all_results)
    if coverage is not None:
        payload["coverage"] = coverage
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
        if args.dry_run:
            payload = dry_run_search_payload(args.product_name, args.category)
        else:
            payload = live_search_payload(args.product_name, args.category)
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
