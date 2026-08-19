from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.search.audit import freeze_run_as_cassette
from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.query_builder import build_search_queries
from src.search.tavily import TavilySearchProvider


PROJECT_ROOT = Path(__file__).resolve().parent
CATEGORY_PATHS = {
    "titanium_dioxide": PROJECT_ROOT / "config" / "categories" / "titanium_dioxide.yaml",
    "phosphoric_acid": PROJECT_ROOT / "config" / "categories" / "phosphoric_acid.yaml",
}


def _parse_scalar(value: str) -> str | int | float | bool | None:
    if value.startswith('"') and value.endswith('"'):
        return json.loads(value)
    if value in {"true", "false", "null"}:
        return json.loads(value)
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _parse_yaml_block(
    lines: list[tuple[int, str]], start: int, indent: int
) -> tuple[dict[str, Any] | list[Any], int]:
    is_list = lines[start][1].startswith("- ")
    result: dict[str, Any] | list[Any] = [] if is_list else {}
    index = start

    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent:
            raise ValueError("invalid YAML indentation")

        if is_list:
            if not content.startswith("- "):
                raise ValueError("mixed YAML collection types")
            assert isinstance(result, list)
            result.append(_parse_scalar(content[2:].strip()))
            index += 1
            continue

        if content.startswith("- ") or ":" not in content:
            raise ValueError("invalid YAML mapping entry")
        assert isinstance(result, dict)
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            index += 1
            continue

        index += 1
        if index >= len(lines) or lines[index][0] <= indent:
            result[key] = {}
            continue
        child_indent = lines[index][0]
        child, index = _parse_yaml_block(lines, index, child_indent)
        result[key] = child

    return result, index


def load_category(name: str) -> dict[str, Any]:
    path = CATEGORY_PATHS[name]
    with path.open("r", encoding="utf-8") as category_file:
        lines = [
            (len(raw_line) - len(raw_line.lstrip(" ")), raw_line.strip())
            for raw_line in category_file
            if raw_line.strip() and not raw_line.lstrip().startswith("#")
        ]
    if not lines:
        return {}
    parsed, end = _parse_yaml_block(lines, 0, lines[0][0])
    if end != len(lines) or not isinstance(parsed, dict):
        raise ValueError("category YAML must contain one mapping")
    return parsed


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
    queries = build_search_queries(product_name, category)
    return {
        "dry_run": True,
        "queries": queries,
        "estimated_credits": SearchBudget.estimate_credits(len(queries)),
    }


def live_search_payload(
    product_name: str,
    category: str | None = None,
) -> dict[str, Any]:
    queries = build_search_queries(product_name, category)
    budget = SearchBudget()
    live_provider = TavilySearchProvider(budget=budget)
    provider = CachedSearchProvider(
        live_provider,
        provider_name=live_provider.provider_name,
        depth=live_provider.search_depth,
    )
    query_results = [
        {
            "query": query,
            "results": [asdict(result) for result in provider.search(query)],
        }
        for query in queries
    ]
    return {
        "dry_run": False,
        "queries": query_results,
        "execution_credits": budget.execution_credits,
        "monthly_credits": budget.monthly_credits(),
    }


def main(argv: list[str] | None = None) -> int:
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
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
