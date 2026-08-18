from datetime import UTC, datetime

import pytest

from src.evidence import evidenced_specification, unknown_specification
from src.metrics import calculate_rates, validate_metrics
from src.models import (
    TBD,
    UNKNOWN,
    ComplianceStatus,
    Evidence,
    PipelineMetrics,
)
from src.technical_matching import (
    HardConstraint,
    WeightedProperty,
    evaluate_exact_hard_constraint,
    evaluate_membership_hard_constraint,
    evaluate_phosphoric_acid_concentration,
    evaluate_phosphoric_acid_grade,
    evaluate_specification_compliance,
    evaluate_technical_match,
)


def evidence() -> Evidence:
    return Evidence(
        source_url="https://manufacturer.test/tds.pdf",
        source_type="TDS",
        document_name="TDS",
        page=1,
        evidence_excerpt="Documented property",
        retrieved_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )


def test_hard_constraint_failure_is_eliminatory() -> None:
    result = evaluate_technical_match(
        hard_constraints=[
            HardConstraint("chemistry", ComplianceStatus.FAIL, "rutile", "anatase")
        ],
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status is ComplianceStatus.FAIL
    assert result.eligible is False
    assert result.technical_match == TBD


def test_unknown_hard_constraint_does_not_pass() -> None:
    result = evaluate_technical_match(
        hard_constraints=[HardConstraint("treatment", ComplianceStatus.UNKNOWN)],
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status is ComplianceStatus.UNKNOWN
    assert result.eligible == UNKNOWN


def test_undefined_hard_constraints_remain_tbd() -> None:
    result = evaluate_technical_match(
        hard_constraints=TBD,
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status == TBD
    assert result.technical_match == TBD


def test_unknown_weight_remains_tbd_even_when_hard_constraints_pass() -> None:
    result = evaluate_technical_match(
        hard_constraints=[HardConstraint("chemistry", ComplianceStatus.PASS)],
        weighted_properties=[WeightedProperty("brightness")],
    )

    assert result.eligible is True
    assert result.technical_match == TBD


def test_no_default_scoring_formula_is_chosen() -> None:
    properties = [WeightedProperty("brightness", weight=1.0, property_match=0.8)]
    result = evaluate_technical_match(
        hard_constraints=[HardConstraint("chemistry", ComplianceStatus.PASS)],
        weighted_properties=properties,
    )

    assert result.technical_match == TBD


def test_human_supplied_formula_can_be_used() -> None:
    properties = [WeightedProperty("brightness", weight=1.0, property_match=0.8)]
    result = evaluate_technical_match(
        hard_constraints=[HardConstraint("chemistry", ComplianceStatus.PASS)],
        weighted_properties=properties,
        score_formula=lambda items: float(items[0].property_match),
    )

    assert result.technical_match == pytest.approx(0.8)


def test_anatase_candidate_is_eliminated_by_crystal_form() -> None:
    result = evaluate_technical_match(
        hard_constraints=[
            evaluate_exact_hard_constraint(
                property_name="crystal_form",
                expected="rutile",
                actual="anatase",
            )
        ],
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status is ComplianceStatus.FAIL
    assert result.eligible is False


def test_candidate_without_coatings_support_is_eliminated() -> None:
    result = evaluate_technical_match(
        hard_constraints=[
            evaluate_membership_hard_constraint(
                property_name="application_must_support",
                expected="coatings",
                actual_values=["plastics"],
            )
        ],
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status is ComplianceStatus.FAIL
    assert result.eligible is False


def test_candidate_meeting_all_hard_constraints_is_not_eliminated() -> None:
    result = evaluate_technical_match(
        hard_constraints=[
            evaluate_exact_hard_constraint(
                property_name="crystal_form", expected="rutile", actual="rutile"
            ),
            evaluate_exact_hard_constraint(
                property_name="product_category",
                expected="titanium_dioxide_pigment",
                actual="titanium_dioxide_pigment",
            ),
            evaluate_membership_hard_constraint(
                property_name="application_must_support",
                expected="coatings",
                actual_values=["coatings"],
            ),
        ],
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status is ComplianceStatus.PASS
    assert result.eligible is True
    assert result.technical_match == TBD


def test_low_tio2_content_does_not_eliminate_candidate() -> None:
    weighted_property = WeightedProperty(
        property_name="tio2_content",
        weight="TBD_HUMAN",
        property_match=0.1,
    )
    result = evaluate_technical_match(
        hard_constraints=[
            evaluate_exact_hard_constraint(
                property_name="crystal_form", expected="rutile", actual="rutile"
            ),
            evaluate_exact_hard_constraint(
                property_name="product_category",
                expected="titanium_dioxide_pigment",
                actual="titanium_dioxide_pigment",
            ),
            evaluate_membership_hard_constraint(
                property_name="application_must_support",
                expected="coatings",
                actual_values=["coatings"],
            ),
        ],
        weighted_properties=[weighted_property],
    )

    assert result.eligible is True
    assert result.technical_match == TBD
    assert result.weighted_properties == (weighted_property,)
    assert weighted_property.weight == "TBD_HUMAN"


def test_unknown_hard_constraint_value_never_approves_candidate() -> None:
    result = evaluate_technical_match(
        hard_constraints=[
            evaluate_exact_hard_constraint(
                property_name="crystal_form", expected="rutile", actual=UNKNOWN
            )
        ],
        weighted_properties=TBD,
    )

    assert result.hard_constraints_status is ComplianceStatus.UNKNOWN
    assert result.eligible == UNKNOWN


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"minimum": 75.0}, ComplianceStatus.PASS),
        ({"range_lower": 70.0, "range_upper": 80.0}, ComplianceStatus.PASS),
        ({"typical": 76.0}, ComplianceStatus.PASS),
        ({"nominal": 74.9}, ComplianceStatus.FAIL),
        ({}, ComplianceStatus.UNKNOWN),
    ],
)
def test_phosphoric_acid_concentration_rules(
    values: dict[str, float], expected: ComplianceStatus
) -> None:
    assert (
        evaluate_phosphoric_acid_concentration(unit="% w/w", **values) is expected
    )


def test_concentration_without_ww_basis_is_unknown() -> None:
    assert (
        evaluate_phosphoric_acid_concentration(unit="%", minimum=80.0)
        is ComplianceStatus.UNKNOWN
    )


@pytest.mark.parametrize("grade", ["technical", "industrial"])
def test_technical_and_industrial_grades_are_equivalent(grade: str) -> None:
    result = evaluate_phosphoric_acid_grade(grade)

    assert result.compliance is ComplianceStatus.PASS
    assert result.commercial_grade_equivalence == "EQUIVALENT"


@pytest.mark.parametrize("grade", ["food", "pharma grade"])
def test_food_and_pharma_do_not_fail_but_are_flagged(grade: str) -> None:
    result = evaluate_phosphoric_acid_grade(grade)

    assert result.compliance is ComplianceStatus.PASS
    assert result.commercial_grade_equivalence == "NOT_EQUIVALENT"


def test_unmapped_grade_is_unknown_until_human_rule_exists() -> None:
    assert (
        evaluate_phosphoric_acid_grade("reagent").compliance
        is ComplianceStatus.UNKNOWN
    )


def test_case_b_compliance_fail_precedes_unknown() -> None:
    failing = evidenced_specification(
        name="concentration",
        value=74.0,
        unit="% w/w",
        evidence=[evidence()],
        compliance=ComplianceStatus.FAIL,
    )
    unknown = unknown_specification(name="grade")

    assert (
        evaluate_specification_compliance([failing, unknown])
        is ComplianceStatus.FAIL
    )


def test_case_b_compliance_requires_every_property_to_pass() -> None:
    passing = evidenced_specification(
        name="concentration",
        value=75.0,
        unit="% w/w",
        evidence=[evidence()],
        compliance=ComplianceStatus.PASS,
    )
    unknown = unknown_specification(name="grade")

    assert (
        evaluate_specification_compliance([passing, unknown])
        is ComplianceStatus.UNKNOWN
    )
    assert (
        evaluate_specification_compliance([passing, passing])
        is ComplianceStatus.PASS
    )


def test_pipeline_rates_follow_documented_formulas() -> None:
    metrics = PipelineMetrics(
        fetch_attempted=10,
        fetch_success=6,
        fetch_blocked=1,
        fetch_timeout=1,
        fetch_form_required=1,
        fetch_js_required=1,
        pdf_candidates=3,
        pdf_downloaded=2,
        pdf_parseable=1,
        pdf_scanned=1,
        extraction_attempted=4,
        extraction_success=3,
        candidate_products=5,
        verified_candidates=2,
    )
    rates = calculate_rates(metrics)

    assert rates.fetch_success_rate == pytest.approx(0.6)
    assert rates.extraction_success_rate == pytest.approx(0.75)
    assert rates.end_to_end_success_rate == pytest.approx(0.4)


def test_zero_denominators_are_unknown() -> None:
    rates = calculate_rates(PipelineMetrics())

    assert rates.fetch_success_rate == UNKNOWN
    assert rates.extraction_success_rate == UNKNOWN
    assert rates.end_to_end_success_rate == UNKNOWN


def test_metrics_reject_inconsistent_fetch_totals() -> None:
    with pytest.raises(ValueError, match="terminal fetch states"):
        validate_metrics(PipelineMetrics(fetch_attempted=1))


def test_metrics_reject_overlapping_pdf_counters() -> None:
    with pytest.raises(ValueError, match="cannot exceed downloaded"):
        validate_metrics(
            PipelineMetrics(
                pdf_candidates=1,
                pdf_downloaded=1,
                pdf_parseable=1,
                pdf_scanned=1,
            )
        )
