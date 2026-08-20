import json
import subprocess
import sys

import pytest

from research import dry_run_search_payload, load_category, status_payload


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
