from __future__ import annotations

from collections.abc import Callable, Iterable, Set
from dataclasses import dataclass, field

from src.models import (
    NOT_EVALUATED,
    TBD,
    TBD_HUMAN,
    UNKNOWN,
    ComplianceStatus,
    Scalar,
    Specification,
)


@dataclass(frozen=True, slots=True)
class HardConstraint:
    property_name: str
    status: ComplianceStatus
    expected: Scalar = TBD
    actual: Scalar = UNKNOWN


@dataclass(frozen=True, slots=True)
class WeightedProperty:
    property_name: str
    weight: float | str = TBD
    property_match: float | str = UNKNOWN

    def __post_init__(self) -> None:
        if isinstance(self.weight, float) or isinstance(self.weight, int):
            if isinstance(self.weight, bool) or self.weight < 0:
                raise ValueError("weight must be non-negative")
        elif self.weight not in {TBD, TBD_HUMAN}:
            raise ValueError("unknown weights must remain TBD or TBD_HUMAN")

        if isinstance(self.property_match, float) or isinstance(self.property_match, int):
            if isinstance(self.property_match, bool) or not 0 <= self.property_match <= 1:
                raise ValueError("property_match must be between 0 and 1")
        elif self.property_match != UNKNOWN:
            raise ValueError("missing property matches must remain UNKNOWN")


@dataclass(frozen=True, slots=True)
class TechnicalMatchResult:
    hard_constraints: tuple[HardConstraint, ...] | str
    weighted_properties: tuple[WeightedProperty, ...] | str
    hard_constraints_status: ComplianceStatus | str
    eligible: bool | str
    technical_match: float | str = TBD


ScoreFormula = Callable[[tuple[WeightedProperty, ...]], float]


def evaluate_technical_match(
    *,
    hard_constraints: Iterable[HardConstraint] | str,
    weighted_properties: Iterable[WeightedProperty] | str,
    score_formula: ScoreFormula | None = None,
) -> TechnicalMatchResult:
    if isinstance(hard_constraints, str):
        if hard_constraints not in {TBD, TBD_HUMAN}:
            raise ValueError("undefined hard constraints must remain TBD or TBD_HUMAN")
        return TechnicalMatchResult(
            hard_constraints=hard_constraints,
            weighted_properties=(
                weighted_properties
                if isinstance(weighted_properties, str)
                else tuple(weighted_properties)
            ),
            hard_constraints_status=hard_constraints,
            eligible=TBD,
        )

    constraints = tuple(hard_constraints)
    weighted = (
        weighted_properties
        if isinstance(weighted_properties, str)
        else tuple(weighted_properties)
    )

    if any(item.status is ComplianceStatus.FAIL for item in constraints):
        return TechnicalMatchResult(
            hard_constraints=constraints,
            weighted_properties=weighted,
            hard_constraints_status=ComplianceStatus.FAIL,
            eligible=False,
        )
    if any(item.status is ComplianceStatus.UNKNOWN for item in constraints):
        return TechnicalMatchResult(
            hard_constraints=constraints,
            weighted_properties=weighted,
            hard_constraints_status=ComplianceStatus.UNKNOWN,
            eligible=UNKNOWN,
        )

    if isinstance(weighted, str):
        if weighted not in {TBD, TBD_HUMAN}:
            raise ValueError("undefined weighted properties must remain TBD or TBD_HUMAN")
        return TechnicalMatchResult(
            hard_constraints=constraints,
            weighted_properties=weighted,
            hard_constraints_status=ComplianceStatus.PASS,
            eligible=True,
        )

    if (
        not weighted
        or any(item.weight in {TBD, TBD_HUMAN} for item in weighted)
        or any(item.property_match == UNKNOWN for item in weighted)
        or score_formula is None
    ):
        return TechnicalMatchResult(
            hard_constraints=constraints,
            weighted_properties=weighted,
            hard_constraints_status=ComplianceStatus.PASS,
            eligible=True,
        )

    score = score_formula(weighted)
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise ValueError("score_formula must return a number between 0 and 1")
    return TechnicalMatchResult(
        hard_constraints=constraints,
        weighted_properties=weighted,
        hard_constraints_status=ComplianceStatus.PASS,
        eligible=True,
        technical_match=float(score),
    )


@dataclass(frozen=True, slots=True)
class GradeEvaluation:
    compliance: ComplianceStatus
    commercial_grade_equivalence: str = NOT_EVALUATED


def evaluate_phosphoric_acid_concentration(
    *,
    unit: str | None,
    minimum: float | None = None,
    range_lower: float | None = None,
    range_upper: float | None = None,
    typical: float | None = None,
    nominal: float | None = None,
    evidenced: bool = True,
) -> ComplianceStatus:
    if not evidenced or unit is None or unit.strip().lower() not in {"% w/w", "w/w %"}:
        return ComplianceStatus.UNKNOWN
    if (range_lower is None) != (range_upper is None):
        return ComplianceStatus.UNKNOWN
    if range_lower is not None and range_upper is not None and range_lower > range_upper:
        raise ValueError("range_lower cannot exceed range_upper")

    passes = (
        minimum is not None and minimum >= 75.0
    ) or (
        range_lower is not None
        and range_upper is not None
        and range_lower <= 75.0 <= range_upper
    ) or (
        range_lower is not None and range_lower >= 75.0
    ) or (
        typical is not None and typical >= 75.0
    ) or (
        nominal is not None and nominal >= 75.0
    )
    if passes:
        return ComplianceStatus.PASS

    supplied_values = [
        value
        for value in (minimum, range_lower, range_upper, typical, nominal)
        if value is not None
    ]
    if supplied_values:
        return ComplianceStatus.FAIL
    return ComplianceStatus.UNKNOWN


def evaluate_phosphoric_acid_grade(
    grade: str | None,
    *,
    evidenced: bool = True,
    incompatible_grades: Set[str] | str = TBD_HUMAN,
) -> GradeEvaluation:
    if not evidenced or grade is None or not grade.strip():
        return GradeEvaluation(ComplianceStatus.UNKNOWN)

    normalized = grade.strip().lower()
    if normalized in {"technical", "industrial"}:
        return GradeEvaluation(ComplianceStatus.PASS, "EQUIVALENT")
    if normalized in {"food", "food grade", "pharma", "pharma grade"}:
        return GradeEvaluation(ComplianceStatus.PASS, "NOT_EQUIVALENT")
    if not isinstance(incompatible_grades, str) and normalized in {
        item.strip().lower() for item in incompatible_grades
    }:
        return GradeEvaluation(ComplianceStatus.FAIL)
    return GradeEvaluation(ComplianceStatus.UNKNOWN)


def evaluate_specification_compliance(
    specifications: Iterable[Specification],
) -> ComplianceStatus:
    items = tuple(specifications)
    if not items:
        return ComplianceStatus.UNKNOWN

    statuses = tuple(item.compliance or ComplianceStatus.UNKNOWN for item in items)
    if ComplianceStatus.FAIL in statuses:
        return ComplianceStatus.FAIL
    if ComplianceStatus.UNKNOWN in statuses:
        return ComplianceStatus.UNKNOWN
    return ComplianceStatus.PASS
