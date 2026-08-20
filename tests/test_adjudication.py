from __future__ import annotations

from src.search.adjudication import (
    aggregate_adjudicated_precision,
    evaluate_adjudicated_results,
    load_adjudicated_results,
)
from src.search.marketplace import MarketplaceDomainRegistry


def _row(url: str, role: str) -> dict[str, object]:
    return {
        "url": url,
        "domain_classification": {"role": role},
    }


def test_human_adjudication_loads_twenty_results_per_case() -> None:
    case_a = load_adjudicated_results("titanium_dioxide")
    case_b = load_adjudicated_results("phosphoric_acid")

    assert len(case_a) == 20
    assert len(case_b) == 20
    assert {item.case for item in case_a} == {"A"}
    assert {item.case for item in case_b} == {"B"}
    assert next(
        item.human_label
        for item in case_a
        if item.domain == "brandessenceresearch.com"
    ) == "NOT_A_COMPANY"
    assert next(
        item.human_label
        for item in case_b
        if item.domain == "www.icl-group.com"
    ) == "MANUFACTURER"


def test_precision_is_calculated_over_predictions_for_each_role() -> None:
    adjudicated = load_adjudicated_results("titanium_dioxide")
    selected = adjudicated[:4]
    rows = [
        _row(selected[0].url, "MANUFACTURER"),
        _row(selected[1].url, "TRADER"),
        _row(selected[2].url, "MANUFACTURER"),
        _row(selected[3].url, "MANUFACTURER"),
    ]

    evaluation = evaluate_adjudicated_results("titanium_dioxide", rows)

    manufacturer = evaluation["precision_by_role"]["MANUFACTURER"]
    assert manufacturer == {
        "correct": 1,
        "predicted": 3,
        "false_positives": 2,
        "precision_percentage": 33.33,
    }
    trader = evaluation["precision_by_role"]["TRADER"]
    assert trader["correct"] == 1
    assert trader["predicted"] == 1
    assert trader["precision_percentage"] == 100.0
    assert evaluation["missing"] == 16


def test_human_labels_do_not_override_result_classification() -> None:
    adjudicated = load_adjudicated_results("phosphoric_acid")
    human_manufacturer = next(
        item for item in adjudicated if item.domain == "www.icl-group.com"
    )

    evaluation = evaluate_adjudicated_results(
        "phosphoric_acid",
        [_row(human_manufacturer.url, "UNKNOWN")],
    )

    result = next(
        row for row in evaluation["results"] if row["domain"] == "www.icl-group.com"
    )
    assert result["human_label"] == "MANUFACTURER"
    assert result["predicted_role"] == "UNKNOWN"
    assert result["comparison"] == "ERROR"


def test_adjudicated_directory_labels_do_not_become_marketplace_controls() -> None:
    registry = MarketplaceDomainRegistry()

    assert not registry.matches_url(
        "https://www.eximpedia.app/product-titanium-dioxide-r-996-export-data"
    )
    assert not registry.matches_url(
        "https://www.veritradecorp.com/en/peru/imports-and-exports"
    )
    assert not registry.matches_url(
        "https://www.australianchemicalsuppliers.com/content/page/phosphoric-acid"
    )


def test_precision_aggregation_preserves_per_role_denominator() -> None:
    case_a = {
        "precision_by_role": {
            "MANUFACTURER": {
                "correct": 1,
                "predicted": 2,
                "false_positives": 1,
            },
            "DISTRIBUTOR": {
                "correct": 1,
                "predicted": 1,
                "false_positives": 0,
            },
            "TRADER": {"correct": 0, "predicted": 0, "false_positives": 0},
        }
    }
    case_b = {
        "precision_by_role": {
            "MANUFACTURER": {
                "correct": 1,
                "predicted": 1,
                "false_positives": 0,
            },
            "DISTRIBUTOR": {
                "correct": 0,
                "predicted": 1,
                "false_positives": 1,
            },
            "TRADER": {"correct": 1, "predicted": 2, "false_positives": 1},
        }
    }

    combined = aggregate_adjudicated_precision([case_a, case_b])

    assert combined["MANUFACTURER"] == {
        "correct": 2,
        "predicted": 3,
        "false_positives": 1,
        "precision_percentage": 66.67,
    }
    assert combined["DISTRIBUTOR"]["precision_percentage"] == 50.0
    assert combined["TRADER"]["precision_percentage"] == 50.0
