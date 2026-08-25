import json
import subprocess
import sys

import pytest

from research import (
    benchmark_payload,
    build_parser,
    dry_run_search_payload,
    llm_classifier_benchmark_plan,
    llm_classifier_dry_run_payload,
    load_category,
    status_payload,
)


def test_status_declares_external_integrations_deferred() -> None:
    payload = status_payload()

    assert payload["project"] == "OniSource"
    assert payload["phase"] == 0
    assert payload["deferred"] == ["llm"]
    assert "search_provider" in payload["implemented"]


def test_category_configs_are_loadable_without_yaml_dependency() -> None:
    titanium = load_category("titanium_dioxide")
    phosphoric = load_category("phosphoric_acid")

    assert titanium["category"] == "Titanium Dioxide"
    assert titanium["hard_constraints"] == {
        "crystal_form": "rutile",
        "product_category": "titanium_dioxide_pigment",
        "application_must_support": "coatings",
    }
    assert titanium["cas_numbers"] == ["13463-67-7", "1317-80-2"]
    assert titanium["branded"] is True
    assert set(titanium["weighted_properties"]) == {
        "tio2_content",
        "process_route",
        "surface_treatment",
        "tinting_strength",
        "oil_absorption",
        "density",
        "particle_size",
        "undertone",
    }
    assert {
        item["weight"] for item in titanium["weighted_properties"].values()
    } == {"TBD_HUMAN"}
    assert phosphoric["matching_mode"] == "SPECIFICATION_COMPLIANCE"
    assert phosphoric["category"] == "Phosphoric Acid"
    assert phosphoric["cas_number"] == "7664-38-2"
    assert phosphoric["branded"] is False
    assert phosphoric["technical_match"] == "NOT_APPLICABLE"
    assert phosphoric["country_semantics"] == "PRODUCTION_PLANT_COUNTRY"


def test_cli_status_returns_json() -> None:
    completed = subprocess.run(
        [sys.executable, "research.py", "status"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["project"] == "OniSource"
    assert payload["deferred"] == ["llm"]


def test_cli_search_dry_run_prints_queries_without_network() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "research.py",
            "search",
            "phosphoric acid",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["dry_run"] is True
    assert payload["estimated_credits"] == 10
    assert len(payload["queries"]) == 5


def test_cli_forces_utf8_without_altering_unicode_text() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "research.py",
            "search",
            "Product ≥ 99%",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert "Product ≥ 99% manufacturer" in completed.stdout


def test_case_b_dry_run_uses_human_cas_from_category_config() -> None:
    payload = dry_run_search_payload("Phosphoric Acid", "Phosphoric Acid")

    assert "7664-38-2 manufacturer" in payload["queries"]
    assert "Phosphoric Acid equivalent" not in payload["queries"]
    assert "Phosphoric Acid alternative" not in payload["queries"]
    assert payload["estimated_credits"] == len(payload["queries"]) * 2


@pytest.mark.parametrize(
    ("category_identifier", "product_name"),
    [
        ("titanium_dioxide", "BILLIONS R996 Titanium Dioxide"),
        ("phosphoric_acid", "Phosphoric Acid"),
    ],
)
def test_phase_zero_dry_run_queries_never_contain_category_identifier_underscores(
    category_identifier: str,
    product_name: str,
) -> None:
    payload = dry_run_search_payload(product_name, category_identifier)

    assert all("_" not in query for query in payload["queries"])


def test_live_search_payload_ends_with_ground_truth_coverage(monkeypatch) -> None:
    import research
    from src.search.models import SearchResult

    result = SearchResult(
        url="https://gjchemical.com/phosphoric-acid",
        title="Phosphoric Acid 75%",
        snippet="",
        content="",
        raw_score=1.0,
        provider="test",
        query="test query",
        retrieved_at="2026-08-20T12:00:00Z",
    )

    class FakeBudget:
        execution_credits = 0

        def monthly_credits(self) -> int:
            return 70

    class FakeLiveProvider:
        provider_name = "test"
        search_depth = "advanced"
        request_parameters = {
            "include_raw_content": True,
            "exclude_domains": [],
        }

        def __init__(self, *, budget: FakeBudget) -> None:
            self.budget = budget

    class FakeCachedProvider:
        def __init__(
            self,
            provider,
            *,
            provider_name: str,
            depth: str,
            request_parameters,
            refresh: bool,
        ) -> None:
            self.provider = provider

        def search(self, query: str) -> list[SearchResult]:
            return [result]

    monkeypatch.setattr(research, "SearchBudget", FakeBudget)
    monkeypatch.setattr(research, "TavilySearchProvider", FakeLiveProvider)
    monkeypatch.setattr(research, "CachedSearchProvider", FakeCachedProvider)

    payload = research.live_search_payload("Phosphoric Acid", "phosphoric_acid")

    assert list(payload)[-1] == "coverage"
    assert payload["coverage"]["negative_appeared"] is False
    assert payload["coverage"]["total"] == "fabricantes 0/4, distribuidores 1/1"


def test_search_requires_explicit_live_flag() -> None:
    parser = build_parser()

    offline = parser.parse_args(
        ["search", "Phosphoric Acid", "--category", "phosphoric_acid"]
    )
    live = parser.parse_args(
        ["search", "Phosphoric Acid", "--category", "phosphoric_acid", "--live"]
    )

    assert offline.live is False
    assert live.live is True


def test_benchmark_has_separate_explicit_live_extract_flag() -> None:
    parser = build_parser()

    offline = parser.parse_args(["benchmark"])
    extract_live = parser.parse_args(
        ["benchmark", "--live-extract", "--refresh-extract-cassettes"]
    )

    assert offline.live is False
    assert offline.live_extract is False
    assert extract_live.live is False
    assert extract_live.live_extract is True
    assert extract_live.refresh_extract_cassettes is True


def test_benchmark_accepts_isolated_validation_sample() -> None:
    parser = build_parser()

    args = parser.parse_args(["benchmark", "--adjudication-sample", "2"])

    assert args.adjudication_sample == 2


def test_llm_classifier_dry_run_has_a_dedicated_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "llm-classifier-dry-run",
            "--cache-dir",
            "temporary-cache",
            "--adjudicated-only",
            "--input-price-per-mtok",
            "1.25",
            "--output-price-per-mtok",
            "4.5",
        ]
    )
    unpriced = parser.parse_args(["llm-classifier-dry-run"])

    assert args.command == "llm-classifier-dry-run"
    assert args.cache_dir == "temporary-cache"
    assert args.adjudicated_only is True
    assert args.input_price_per_mtok == 1.25
    assert args.output_price_per_mtok == 4.5
    assert unpriced.input_price_per_mtok is None
    assert unpriced.output_price_per_mtok is None


def test_llm_classifier_smoke_requires_an_explicit_live_flag() -> None:
    parser = build_parser()

    offline = parser.parse_args(["llm-classifier-smoke"])
    live = parser.parse_args(["llm-classifier-smoke", "--live"])

    assert offline.live is False
    assert live.live is True


def test_llm_classifier_benchmark_requires_an_explicit_live_flag() -> None:
    parser = build_parser()

    offline = parser.parse_args(["llm-classifier-benchmark"])
    live = parser.parse_args(["llm-classifier-benchmark", "--live"])

    assert offline.live is False
    assert live.live is True


def test_llm_classifier_benchmark_plan_has_68_measurable_domains() -> None:
    plan, missing = llm_classifier_benchmark_plan()

    assert len(plan) == 68
    assert len({item["domain_input"].domain for item in plan}) == 68
    assert {item["domain"] for item in missing} == {
        "www.industryresearch.biz",
        "htmcgroup.com",
        "www.grandviewresearch.com",
    }
    assert all(item["reason"] == "EXTRACTION_FAILED" for item in missing)


def test_llm_classifier_dry_run_uses_only_offline_cassettes(
    tmp_path,
    monkeypatch,
) -> None:
    import research

    def reject_live_provider(*args, **kwargs):
        raise AssertionError("LLM dry-run must not construct a live provider")

    monkeypatch.setattr(research, "TavilySearchProvider", reject_live_provider)
    monkeypatch.setattr(research, "TavilyExtractProvider", reject_live_provider)

    payload = llm_classifier_dry_run_payload(
        cache_dir=tmp_path,
        input_price_per_mtok=2.0,
        output_price_per_mtok=5.0,
    )

    assert payload["mode"] == "dry_run"
    assert payload["adjudicated_only"] is False
    assert payload["provider_selected"] is False
    assert payload["network_calls_made"] == 0
    assert payload["prompt_version"] == "v7"
    assert payload["max_content_chars"] == 40_000
    assert [case["case"] for case in payload["cases"]] == ["A", "B"]
    assert all(
        case["unique_domains"] == len(case["domain_pages"])
        for case in payload["cases"]
    )
    assert all(
        case["www_root_domain_pair_count"] == len(case["www_root_domain_pairs"])
        for case in payload["cases"]
    )
    assert all(
        len(case["content_size_diagnostics"]["largest_domains"]) <= 5
        for case in payload["cases"]
    )
    assert all(
        case["evidence_truncated_count"]
        == sum(item["evidence_truncated"] for item in case["domain_pages"])
        for case in payload["cases"]
    )
    assert all(
        case["evidence_truncated_domains"]
        == [
            item["domain"]
            for item in case["domain_pages"]
            if item["evidence_truncated"]
        ]
        for case in payload["cases"]
    )
    assert payload["total_provider_calls_planned"] == sum(
        case["provider_calls_planned"] for case in payload["cases"]
    )
    assert payload["total_prompt_characters"] == sum(
        case["total_prompt_characters"] for case in payload["cases"]
    )
    assert payload["estimated_input_tokens"] == (
        payload["total_prompt_characters"] / 4
    )
    assert payload["estimated_output_tokens"] == (
        payload["total_provider_calls_planned"] * 150
    )
    assert payload["cost_estimate"]["input_price_per_mtok"] == 2.0
    assert payload["cost_estimate"]["output_price_per_mtok"] == 5.0
    assert len(list((tmp_path / "_pending").glob("*.prompt.txt"))) == payload[
        "total_provider_calls_planned"
    ]


def test_adjudicated_only_dry_run_reports_found_and_absent_labeled_domains(
    tmp_path,
) -> None:
    payload = llm_classifier_dry_run_payload(
        cache_dir=tmp_path,
        adjudicated_only=True,
    )

    assert payload["adjudicated_only"] is True
    assert "cost_estimate" not in payload
    for case in payload["cases"]:
        adjudication = case["adjudication"]
        found = adjudication["labeled_domains_found"]
        absent = adjudication["labeled_domains_absent"]
        assert adjudication["labeled_domains_found_count"] == len(found)
        assert adjudication["labeled_domains_absent_count"] == len(absent)
        assert adjudication["labeled_domains_total"] == len(found) + len(absent)
        assert set(found).isdisjoint(absent)
        assert case["unique_domains"] == len(found)
        assert case["provider_calls_planned"] == len(found)
        diagnosis = adjudication["absent_domain_diagnosis"]
        assert sum(diagnosis["counts"].values()) == len(absent)
        assert set(diagnosis["domains"]) == {
            "NOT_IN_SEARCH_RESULTS",
            "IN_SEARCH_NOT_EXTRACTED",
            "EXTRACTION_FAILED",
        }

    case_b_diagnosis = payload["cases"][1]["adjudication"][
        "absent_domain_diagnosis"
    ]
    diagnosed_search_domains = {
        item["domain"]
        for category in ("IN_SEARCH_NOT_EXTRACTED", "EXTRACTION_FAILED")
        for item in case_b_diagnosis["domains"][category]
    }
    assert "www.grandviewresearch.com" in diagnosed_search_domains


def test_llm_dry_run_prices_must_be_supplied_together(tmp_path) -> None:
    with pytest.raises(ValueError, match="must be provided together"):
        llm_classifier_dry_run_payload(
            cache_dir=tmp_path,
            input_price_per_mtok=1.0,
        )


def test_phase_zero_benchmark_defaults_to_offline_cassettes(monkeypatch) -> None:
    import research

    def reject_live_provider(*args, **kwargs):
        raise AssertionError("offline benchmark must not construct Tavily")

    monkeypatch.setattr(research, "TavilySearchProvider", reject_live_provider)

    payload = benchmark_payload()

    assert payload["provider_mode"] == "cassette"
    assert payload["query_set_version"] == "phase0-search-v2"
    assert payload["total_credits_consumed"] == 0
    assert payload["adjudicated_recall_by_role"]["MANUFACTURER"] == {
        "correct": 2,
        "human_total": 5,
        "false_negatives": 3,
        "recall_percentage": 40.0,
    }
    assert payload["adjudicated_confusion_matrix"]["columns"][-2:] == [
        "NOT_A_COMPANY",
        "MARKETPLACE",
    ]
    assert [case["query_count"] for case in payload["cases"]] == [15, 12]
    assert payload["cases"][0]["coverage"]["total"] == (
        "fabricantes 3/3, distribuidores 0/2"
    )
    assert payload["cases"][1]["coverage"]["negative_appeared"] is True


def test_offline_benchmark_classifies_results_and_compares_ground_truth() -> None:
    payload = benchmark_payload()

    for case in payload["cases"]:
        classification = case["company_classification"]
        assert classification["result_count"] > 0
        assert len(classification["results"]) == classification["result_count"]
        assert all(
            result["entity_classifications"]
            for result in classification["results"]
        )

    case_a = payload["cases"][0]["company_classification"]
    case_b = payload["cases"][1]["company_classification"]
    assert case_a["result_count"] == 150
    assert case_a["ground_truth_comparison"]["summary"] == {
        "hits": 2,
        "errors": 1,
        "not_found": 2,
        "evaluated": 3,
    }
    assert case_b["result_count"] == 120
    assert case_b["ground_truth_comparison"]["summary"] == {
        "hits": 0,
        "errors": 2,
        "not_found": 5,
        "evaluated": 2,
    }
    assert case_b["ground_truth_comparison"]["negative"] == {
        "appeared": True,
        "violations": 0,
        "behavior": "PASS",
    }


def test_refresh_cassettes_requires_explicit_live_mode() -> None:
    with pytest.raises(ValueError, match="requires live"):
        benchmark_payload(refresh_cassettes=True)


def test_refresh_extract_cassettes_requires_explicit_extract_live_mode() -> None:
    with pytest.raises(ValueError, match="requires live_extract"):
        benchmark_payload(refresh_extract_cassettes=True)


def test_missing_extract_cassettes_are_reported_explicitly(tmp_path) -> None:
    payload = benchmark_payload(extract_cassette_dir=tmp_path / "missing")

    assert [case["extraction"]["provider_mode"] for case in payload["cases"]] == [
        "NOT_AVAILABLE",
        "NOT_AVAILABLE",
    ]
    assert payload["total_extraction_credits_consumed"] == 0
