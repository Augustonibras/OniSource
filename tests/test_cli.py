import json
import subprocess
import sys

from research import load_category, status_payload


def test_status_declares_external_integrations_deferred() -> None:
    payload = status_payload()

    assert payload["project"] == "OniSource"
    assert payload["phase"] == 0
    assert payload["deferred"] == ["internet", "tavily", "llm"]


def test_category_configs_are_loadable_without_yaml_dependency() -> None:
    titanium = load_category("titanium_dioxide")
    phosphoric = load_category("phosphoric_acid")

    assert titanium["weights"] == "TBD"
    assert titanium["hard_constraints"] == "TBD_HUMAN"
    assert phosphoric["matching_mode"] == "SPECIFICATION_COMPLIANCE"
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
    assert "internet" in payload["deferred"]
