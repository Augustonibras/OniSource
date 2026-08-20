import json
import subprocess
import sys

import pytest

from research import (
    benchmark_payload,
    build_parser,
    dry_run_search_payload,
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

        def __init__(self, *, budget: FakeBudget) -> None:
            self.budget = budget

    class FakeCachedProvider:
        def __init__(self, provider, *, provider_name: str, depth: str) -> None:
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


def test_phase_zero_benchmark_defaults_to_offline_cassettes(monkeypatch) -> None:
    import research

    def reject_live_provider(*args, **kwargs):
        raise AssertionError("offline benchmark must not construct Tavily")

    monkeypatch.setattr(research, "TavilySearchProvider", reject_live_provider)

    payload = benchmark_payload()

    assert payload["provider_mode"] == "cassette"
    assert payload["query_set_version"] == "phase0-search-v1"
    assert payload["total_credits_consumed"] == 0
    assert [case["query_count"] for case in payload["cases"]] == [15, 12]
    assert payload["cases"][0]["coverage"]["total"] == (
        "fabricantes 2/3, distribuidores 0/2"
    )
    assert payload["cases"][1]["coverage"]["negative_appeared"] is True
