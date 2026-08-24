from __future__ import annotations

import argparse
import json
import math
import statistics
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
    ExtractCassetteNotFoundError,
)
from src.extract.models import ExtractResult
from src.extract.provider import ExtractProvider
from src.extract.tavily import TavilyExtractProvider
from src.search.audit import freeze_cache_as_cassette, freeze_run_as_cassette
from src.search.adjudication import (
    aggregate_adjudicated_evaluations,
    load_adjudicated_results,
)
from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.cassette import CassetteSearchProvider
from src.search.company_classifier import (
    DEFAULT_LLM_CACHE_DIR,
    LLM_FAILURE_REASONS,
    MAX_CONTENT_CHARS,
    PROMPT_VERSION,
    LLMCompanyClassifier,
    DomainClassificationInput,
    budget_extracted_content,
    group_extracted_pages_by_domain,
    normalize_classifier_domain,
)
from src.search.company_evaluation import build_company_classification_report
from src.search.coverage import build_ground_truth_coverage
from src.search.extraction_selection import (
    MAX_EXTRACTIONS_PER_CASE,
    attach_extraction_signals,
    select_extraction_urls,
)
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
        "product_context": "titanium dioxide, rutile grade, CAS 13463-67-7",
    },
    {
        "case": "B",
        "product_name": "Phosphoric Acid",
        "category": "phosphoric_acid",
        "product_context": "phosphoric acid, CAS 7664-38-2",
    },
)
ESTIMATED_OUTPUT_TOKENS_PER_CALL = 150


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
    benchmark_parser.add_argument(
        "--adjudication-sample",
        type=int,
        choices=(1, 2),
        default=1,
        help="Select the isolated human adjudication set (default: 1)",
    )
    llm_dry_run_parser = subparsers.add_parser(
        "llm-classifier-dry-run",
        help="Estimate Phase 0 LLM classification inputs without provider calls",
    )
    llm_dry_run_parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_LLM_CACHE_DIR),
        help="Write pending prompts below this ignored cache directory",
    )
    llm_dry_run_parser.add_argument(
        "--adjudicated-only",
        action="store_true",
        help="Plan only domains labeled by humans in adjudication samples 1 and 2",
    )
    llm_dry_run_parser.add_argument("--input-price-per-mtok", type=float)
    llm_dry_run_parser.add_argument("--output-price-per-mtok", type=float)
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
        results = attach_extraction_signals(provider.search(query))
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
            "url_limit": MAX_EXTRACTIONS_PER_CASE,
            "candidate_urls": len(selected_urls),
            "attempted_urls": 0,
            "successful_urls": 0,
            "failed_urls": 0,
            "batches": 0,
            "cache_hits": 0,
            "missing_cassette_batches": 0,
            "missing_cassette_urls": 0,
            "missing_cassette_url_values": [],
            "credits_consumed": 0,
        }

    credits_before = budget.execution_credits if budget is not None else 0
    extracted: dict[str, str] = {}
    batches = _extract_batches(selected_urls)
    cache_hits = 0
    missing_cassette_batches = 0
    missing_cassette_urls = 0
    missing_cassette_url_values: list[str] = []
    attempted_url_values: list[str] = []
    for batch in batches:
        try:
            batch_results: list[ExtractResult] = provider.extract(batch)
        except ExtractCassetteNotFoundError:
            if provider_mode != "cassette":
                raise
            missing_cassette_batches += 1
            missing_cassette_urls += len(batch)
            missing_cassette_url_values.extend(batch)
            continue
        attempted_url_values.extend(batch)
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
        "url_limit": MAX_EXTRACTIONS_PER_CASE,
        "candidate_urls": len(selected_urls),
        "attempted_urls": len(attempted_url_values),
        "successful_urls": len(extracted),
        "failed_urls": len(attempted_url_values) - len(extracted),
        "batches": len(batches),
        "cache_hits": cache_hits,
        "missing_cassette_batches": missing_cassette_batches,
        "missing_cassette_urls": missing_cassette_urls,
        "missing_cassette_url_values": missing_cassette_url_values,
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
    adjudication_sample: int = 1,
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
                    adjudication_sample=adjudication_sample,
                ),
                "extraction": extraction,
            }
        )

    combined_adjudication = aggregate_adjudicated_evaluations(
        case["company_classification"]["adjudicated_results_evaluation"]
        for case in case_payloads
    )
    payload: dict[str, Any] = {
        "benchmark": "OniSource Phase 0",
        "provider_mode": "live" if live else "cassette",
        "extract_provider_mode": extract_provider_mode,
        "query_set_version": QUERY_SET_VERSION,
        "adjudication_sample": adjudication_sample,
        "cases": case_payloads,
        "adjudicated_precision_by_role": combined_adjudication[
            "precision_by_role"
        ],
        "adjudicated_recall_by_role": combined_adjudication["recall_by_role"],
        "adjudicated_confusion_matrix": combined_adjudication[
            "confusion_matrix"
        ],
        "adjudicated_blocked_manufacturers": combined_adjudication[
            "blocked_manufacturers"
        ],
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


def _www_root_domain_pairs(domains: list[str]) -> list[dict[str, str]]:
    domain_set = set(domains)
    return [
        {"www_domain": domain, "root_domain": domain.removeprefix("www.")}
        for domain in sorted(domain_set)
        if domain.startswith("www.") and domain.removeprefix("www.") in domain_set
    ]


def _content_size_diagnostics(
    domain_inputs: tuple[DomainClassificationInput, ...],
) -> dict[str, object]:
    sizes = sorted(len(item.extracted_content) for item in domain_inputs)
    if not sizes:
        distribution: dict[str, int | float | str] = {
            "minimum": "NOT_DEFINED",
            "median": "NOT_DEFINED",
            "p90": "NOT_DEFINED",
            "maximum": "NOT_DEFINED",
        }
    else:
        p90_index = max(0, math.ceil(len(sizes) * 0.9) - 1)
        distribution = {
            "minimum": sizes[0],
            "median": statistics.median(sizes),
            "p90": sizes[p90_index],
            "maximum": sizes[-1],
        }
    largest = sorted(
        (
            {"domain": item.domain, "content_characters": len(item.extracted_content)}
            for item in domain_inputs
        ),
        key=lambda item: (-item["content_characters"], item["domain"]),
    )[:5]
    return {
        "distribution": distribution,
        "p90_method": "nearest_rank",
        "domains_exceeding_max_content_chars": sum(
            len(item.extracted_content) > MAX_CONTENT_CHARS
            for item in domain_inputs
        ),
        "largest_domains": largest,
    }


def _human_labeled_domains(category: str) -> set[str]:
    return {
        normalize_classifier_domain(item.domain)
        for sample in (1, 2)
        for item in load_adjudicated_results(category, sample=sample)
    }


def _urls_by_domain(results: list[SearchResult]) -> dict[str, list[str]]:
    indexed: dict[str, list[str]] = {}
    for result in results:
        domain = normalize_classifier_domain(result.url)
        urls = indexed.setdefault(domain, [])
        if result.url not in urls:
            urls.append(result.url)
    return indexed


def diagnose_labeled_domain_coverage(
    labeled_absent: list[str],
    results: list[SearchResult],
    attempted_urls: list[str],
    extracted_content_by_url: dict[str, str],
) -> dict[str, object]:
    search_urls = _urls_by_domain(results)
    attempted_set = set(attempted_urls)
    attempted_by_domain = _urls_by_domain(
        [result for result in results if result.url in attempted_set]
    )
    extracted_domains = {
        normalize_classifier_domain(url) for url in extracted_content_by_url
    }
    categories = {
        "NOT_IN_SEARCH_RESULTS": [],
        "IN_SEARCH_NOT_EXTRACTED": [],
        "EXTRACTION_FAILED": [],
    }
    for domain in sorted(labeled_absent):
        if domain not in search_urls:
            category = "NOT_IN_SEARCH_RESULTS"
            source_url = None
        elif domain in attempted_by_domain and domain not in extracted_domains:
            category = "EXTRACTION_FAILED"
            source_url = attempted_by_domain[domain][0]
        else:
            category = "IN_SEARCH_NOT_EXTRACTED"
            source_url = search_urls[domain][0]
        categories[category].append(
            {"domain": domain, "source_url": source_url}
        )
    return {
        "counts": {
            category: len(items) for category, items in categories.items()
        },
        "domains": categories,
    }


def _token_and_cost_estimate(
    *,
    calls: int,
    prompt_characters: int,
    input_price_per_mtok: float | None,
    output_price_per_mtok: float | None,
) -> dict[str, object]:
    input_tokens = prompt_characters / 4
    output_tokens = calls * ESTIMATED_OUTPUT_TOKENS_PER_CALL
    estimate: dict[str, object] = {
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
    }
    if input_price_per_mtok is None and output_price_per_mtok is None:
        return estimate
    if input_price_per_mtok is None or output_price_per_mtok is None:
        raise ValueError("input and output prices must be provided together")
    if input_price_per_mtok < 0 or output_price_per_mtok < 0:
        raise ValueError("input and output prices must be non-negative")
    input_cost = input_tokens / 1_000_000 * input_price_per_mtok
    output_cost = output_tokens / 1_000_000 * output_price_per_mtok
    estimate["cost_estimate"] = {
        "input_price_per_mtok": input_price_per_mtok,
        "output_price_per_mtok": output_price_per_mtok,
        "estimated_input_cost": input_cost,
        "estimated_output_cost": output_cost,
        "estimated_total_cost": input_cost + output_cost,
    }
    return estimate


def llm_classifier_dry_run_payload(
    *,
    cache_dir: str | Path = DEFAULT_LLM_CACHE_DIR,
    extract_cassette_dir: str | Path = DEFAULT_EXTRACT_CASSETTE_DIR,
    adjudicated_only: bool = False,
    input_price_per_mtok: float | None = None,
    output_price_per_mtok: float | None = None,
) -> dict[str, Any]:
    """Estimate cache-miss LLM inputs using only committed offline cassettes."""

    _token_and_cost_estimate(
        calls=0,
        prompt_characters=0,
        input_price_per_mtok=input_price_per_mtok,
        output_price_per_mtok=output_price_per_mtok,
    )
    search_provider = CassetteSearchProvider()
    extract_path = Path(extract_cassette_dir)
    if not extract_path.is_dir() or not any(extract_path.glob("*.json")):
        raise FileNotFoundError("offline extraction cassettes are required")
    extract_provider = CassetteExtractProvider(extract_path)
    case_payloads: list[dict[str, object]] = []
    total_calls = 0
    total_characters = 0
    total_failures = {reason: 0 for reason in LLM_FAILURE_REASONS}

    for case in PHASE_ZERO_CASES:
        category = case["category"]
        queries = build_search_queries(
            case["product_name"],
            category,
            category_config=load_search_category_config(category),
        )
        _, results = _execute_queries(search_provider, queries)
        selected_urls = select_extraction_urls(results)
        extracted_content, extraction = _extract_case_content(
            results,
            extract_provider,
            provider_mode="cassette",
        )
        all_domain_inputs = group_extracted_pages_by_domain(
            results,
            extracted_content,
        )
        adjudication: dict[str, object] | None = None
        if adjudicated_only:
            labeled_domains = _human_labeled_domains(category)
            extracted_domains = {item.domain for item in all_domain_inputs}
            labeled_found = sorted(labeled_domains.intersection(extracted_domains))
            labeled_absent = sorted(labeled_domains.difference(extracted_domains))
            domain_inputs = tuple(
                item for item in all_domain_inputs if item.domain in labeled_domains
            )
            adjudication = {
                "labeled_domains_total": len(labeled_domains),
                "labeled_domains_found_count": len(labeled_found),
                "labeled_domains_found": labeled_found,
                "labeled_domains_absent_count": len(labeled_absent),
                "labeled_domains_absent": labeled_absent,
                "absent_domain_diagnosis": diagnose_labeled_domain_coverage(
                    labeled_absent,
                    results,
                    [
                        url
                        for url in selected_urls
                        if url
                        not in set(extraction["missing_cassette_url_values"])
                    ],
                    extracted_content,
                ),
            }
        else:
            domain_inputs = all_domain_inputs
        classifier = LLMCompanyClassifier(
            None,
            cache_dir,
            on_miss="dry_run",
        )
        evidence_truncated_domains: list[str] = []
        for domain_input in domain_inputs:
            classification = classifier.classify(
                domain_input.domain,
                domain_input.title,
                domain_input.extracted_content,
                case["product_context"],
                marketplace_signal=domain_input.marketplace_signal,
                marketplace_signal_reason="; ".join(
                    domain_input.marketplace_signal_reasons
                ),
                noise_signal=domain_input.noise_signal,
                noise_signal_reason="; ".join(domain_input.noise_signal_reasons),
            )
            if classification.evidence_truncated:
                evidence_truncated_domains.append(domain_input.domain)

        metrics = classifier.execution_metrics
        calls = int(metrics["provider_calls_planned"])
        characters = int(metrics["total_prompt_characters"])
        failure_counts = metrics["failure_counts"]
        if not isinstance(failure_counts, dict):
            raise TypeError("classifier failure_counts must be a mapping")
        total_calls += calls
        total_characters += characters
        for reason in LLM_FAILURE_REASONS:
            total_failures[reason] += int(failure_counts[reason])
        domains = [item.domain for item in domain_inputs]
        www_pairs = _www_root_domain_pairs(domains)
        case_payload: dict[str, object] = {
            "case": case["case"],
            "category": category,
            "product_context": case["product_context"],
            "extracted_urls": extraction["successful_urls"],
            "unique_domains": len(domain_inputs),
            "www_root_domain_pair_count": len(www_pairs),
            "www_root_domain_pairs": www_pairs,
            "domain_pages": [
                {
                    "domain": item.domain,
                    "pages_merged": item.page_count,
                    "content_characters": len(item.extracted_content),
                    "marketplace_signal": item.marketplace_signal,
                    "marketplace_signal_reasons": list(
                        item.marketplace_signal_reasons
                    ),
                    "noise_signal": item.noise_signal,
                    "noise_signal_reasons": list(item.noise_signal_reasons),
                    "evidence_truncated": (
                        budget_extracted_content(
                            item.extracted_content
                        ).evidence_truncated
                    ),
                }
                for item in domain_inputs
            ],
            "content_size_diagnostics": _content_size_diagnostics(domain_inputs),
            "provider_calls_planned": calls,
            "evidence_truncated_count": len(evidence_truncated_domains),
            "evidence_truncated_domains": evidence_truncated_domains,
            "total_prompt_characters": characters,
            **_token_and_cost_estimate(
                calls=calls,
                prompt_characters=characters,
                input_price_per_mtok=input_price_per_mtok,
                output_price_per_mtok=output_price_per_mtok,
            ),
            "failure_counts": failure_counts,
        }
        if adjudication is not None:
            case_payload["adjudication"] = adjudication
        case_payloads.append(case_payload)

    payload: dict[str, Any] = {
        "mode": "dry_run",
        "adjudicated_only": adjudicated_only,
        "provider_selected": False,
        "network_calls_made": 0,
        "prompt_version": PROMPT_VERSION,
        "max_content_chars": MAX_CONTENT_CHARS,
        "token_estimation_method": (
            "input characters / 4; output 150 tokens / planned call"
        ),
        "estimated_output_tokens_per_call": ESTIMATED_OUTPUT_TOKENS_PER_CALL,
        "cases": case_payloads,
        "total_provider_calls_planned": total_calls,
        "total_prompt_characters": total_characters,
        **_token_and_cost_estimate(
            calls=total_calls,
            prompt_characters=total_characters,
            input_price_per_mtok=input_price_per_mtok,
            output_price_per_mtok=output_price_per_mtok,
        ),
        "failure_counts": total_failures,
    }
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
            adjudication_sample=args.adjudication_sample,
        )
    elif args.command == "llm-classifier-dry-run":
        payload = llm_classifier_dry_run_payload(
            cache_dir=args.cache_dir,
            adjudicated_only=args.adjudicated_only,
            input_price_per_mtok=args.input_price_per_mtok,
            output_price_per_mtok=args.output_price_per_mtok,
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
