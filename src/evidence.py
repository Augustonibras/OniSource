from __future__ import annotations

from collections.abc import Iterable

from src.models import (
    UNKNOWN,
    ComplianceStatus,
    Evidence,
    PropertyStatus,
    Scalar,
    Specification,
)


def evidenced_specification(
    *,
    name: str,
    value: Scalar,
    unit: str,
    evidence: Iterable[Evidence],
    compliance: ComplianceStatus | None = None,
    commercial_grade_equivalence: str = "NOT_EVALUATED",
) -> Specification:
    items = tuple(evidence)
    return Specification(
        name=name,
        property_status=PropertyStatus.EVIDENCED,
        value=value,
        unit=unit,
        evidence=items,
        sources_consulted=tuple(item.source_url for item in items),
        compliance=compliance,
        commercial_grade_equivalence=commercial_grade_equivalence,
    )


def unknown_specification(
    *,
    name: str,
    sources_consulted: Iterable[str] = (),
    preserved_evidence: Iterable[Evidence] = (),
) -> Specification:
    return Specification(
        name=name,
        property_status=PropertyStatus.UNKNOWN,
        value=UNKNOWN,
        unit=UNKNOWN,
        evidence=tuple(preserved_evidence),
        sources_consulted=tuple(sources_consulted),
        compliance=ComplianceStatus.UNKNOWN,
    )


def has_complete_evidence(specification: Specification) -> bool:
    if specification.property_status is PropertyStatus.UNKNOWN:
        return specification.value == UNKNOWN
    return specification.value != UNKNOWN and bool(specification.evidence)
