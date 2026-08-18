from datetime import UTC, datetime

import pytest

from src.evidence import evidenced_specification, has_complete_evidence, unknown_specification
from src.models import (
    NOT_EVALUATED,
    TBD,
    TBD_HUMAN,
    UNKNOWN,
    CandidateProduct,
    Company,
    Evidence,
    PropertyStatus,
    Specification,
)


def make_evidence(url: str = "https://example.test/tds.pdf") -> Evidence:
    return Evidence(
        source_url=url,
        source_type="TDS",
        document_name="Technical Data Sheet",
        page=1,
        evidence_excerpt="Assay: 75.0% w/w minimum",
        retrieved_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )


def test_evidence_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        Evidence(
            source_url="https://example.test/source",
            source_type="product_page",
            document_name="Product",
            page="NOT_APPLICABLE",
            evidence_excerpt="Industrial grade",
            retrieved_at=datetime(2026, 8, 18, 12, 0),
        )


def test_evidenced_specification_requires_and_links_evidence() -> None:
    evidence = make_evidence()
    specification = evidenced_specification(
        name="concentration",
        value=75.0,
        unit="% w/w",
        evidence=[evidence],
    )

    assert specification.property_status is PropertyStatus.EVIDENCED
    assert specification.sources_consulted == (evidence.source_url,)
    assert has_complete_evidence(specification) is True


def test_unknown_specification_does_not_invent_value() -> None:
    specification = unknown_specification(
        name="country",
        sources_consulted=["https://example.test/company"],
    )

    assert specification.property_status is PropertyStatus.UNKNOWN
    assert specification.value == UNKNOWN
    assert specification.evidence == ()
    assert has_complete_evidence(specification) is True


def test_unknown_specification_can_preserve_conflicting_evidence() -> None:
    first = make_evidence("https://example.test/first")
    second = make_evidence("https://example.test/second")
    specification = unknown_specification(
        name="grade",
        preserved_evidence=[first, second],
    )

    assert specification.value == UNKNOWN
    assert specification.evidence == (first, second)
    assert specification.sources_consulted == (first.source_url, second.source_url)


def test_unknown_property_rejects_factual_value() -> None:
    with pytest.raises(ValueError, match="cannot contain a factual value"):
        Specification(
            name="country",
            property_status=PropertyStatus.UNKNOWN,
            value="Brazil",
        )


def test_evidenced_property_rejects_missing_evidence() -> None:
    with pytest.raises(ValueError, match="require evidence"):
        Specification(
            name="grade",
            property_status=PropertyStatus.EVIDENCED,
            value="technical",
        )


def test_candidate_defaults_keep_pending_human_decisions() -> None:
    candidate = CandidateProduct(
        candidate_id="candidate-1",
        name="Example Product",
        company=Company(name="Example Company"),
    )

    assert candidate.technical_match == TBD
    assert candidate.evidence_confidence == TBD_HUMAN
    assert candidate.brazil_import_viability == NOT_EVALUATED
    assert candidate.commercial_fit == NOT_EVALUATED
    assert candidate.company.official_domain == UNKNOWN
