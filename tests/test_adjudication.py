from __future__ import annotations

from src.search.adjudication import (
    aggregate_adjudicated_evaluations,
    aggregate_adjudicated_precision,
    evaluate_adjudicated_results,
    load_adjudicated_results,
)
from src.search.marketplace import MarketplaceDomainRegistry


def _row(
    url: str,
    role: str,
    *,
    page_type: str = "COMPANY",
    reason_codes: list[str] | None = None,
    evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "url": url,
        "domain_classification": {
            "role": role,
            "page_type": page_type,
            "reason_codes": reason_codes or [],
            "evidence": evidence or [],
        },
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
    manufacturer_recall = evaluation["recall_by_role"]["MANUFACTURER"]
    assert manufacturer_recall == {
        "correct": 1,
        "human_total": 3,
        "false_negatives": 2,
        "recall_percentage": 33.33,
    }
    matrix = evaluation["confusion_matrix"]
    assert "UNKNOWN" in matrix["columns"]
    assert "NOT_A_COMPANY" in matrix["columns"]
    assert matrix["values"]["NOT_A_COMPANY"]["MANUFACTURER"] == 1
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


def test_missed_manufacturer_reports_the_blocking_gate() -> None:
    adjudicated = load_adjudicated_results("titanium_dioxide")
    manufacturer = next(
        item for item in adjudicated if item.domain == "hxtio2.com"
    )
    evaluation = evaluate_adjudicated_results(
        "titanium_dioxide",
        [
            _row(
                manufacturer.url,
                "UNKNOWN",
                reason_codes=["MANUFACTURER_POSITIVE_PRODUCTION_SIGNAL_REQUIRED"],
                evidence=[{"supports": "explicit_manufacturing_evidence"}],
            )
        ],
    )

    assert evaluation["blocked_manufacturers"] == [
        {
            "domain": "hxtio2.com",
            "url": manufacturer.url,
            "predicted_role": "UNKNOWN",
            "blocking_gates": [
                "MANUFACTURER_POSITIVE_PRODUCTION_SIGNAL_REQUIRED"
            ],
        },
        {
            "domain": "www.lomonbillions.global",
            "url": next(
                item.url
                for item in adjudicated
                if item.domain == "www.lomonbillions.global"
            ),
            "predicted_role": "NOT_FOUND",
            "blocking_gates": ["RESULT_NOT_FOUND"],
        },
        {
            "domain": "www.mytio2.com",
            "url": next(
                item.url for item in adjudicated if item.domain == "www.mytio2.com"
            ),
            "predicted_role": "NOT_FOUND",
            "blocking_gates": ["RESULT_NOT_FOUND"],
        },
    ]


def test_combined_evaluation_sums_recall_and_confusion_counts() -> None:
    case_a_label = next(
        item
        for item in load_adjudicated_results("titanium_dioxide")
        if item.domain == "hxtio2.com"
    )
    case_b_label = next(
        item
        for item in load_adjudicated_results("phosphoric_acid")
        if item.domain == "www.icl-group.com"
    )
    case_a = evaluate_adjudicated_results(
        "titanium_dioxide",
        [_row(case_a_label.url, "MANUFACTURER")],
    )
    case_b = evaluate_adjudicated_results(
        "phosphoric_acid",
        [_row(case_b_label.url, "NOT_A_COMPANY", page_type="MARKET_REPORT")],
    )

    combined = aggregate_adjudicated_evaluations([case_a, case_b])

    assert combined["adjudicated"] == 40
    assert combined["matched"] == 2
    assert combined["recall_by_role"]["MANUFACTURER"] == {
        "correct": 1,
        "human_total": 5,
        "false_negatives": 4,
        "recall_percentage": 20.0,
    }
    assert combined["confusion_matrix"]["values"]["MANUFACTURER"] == {
        "MANUFACTURER": 1,
        "DISTRIBUTOR": 0,
        "TRADER": 0,
        "UNKNOWN": 0,
        "NOT_A_COMPANY": 1,
        "MARKETPLACE": 0,
    }
