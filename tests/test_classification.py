from src.company_classification import classify_company
from src.document_classification import classify_document
from src.models import (
    CompanyClassification,
    CompanyVerification,
    Document,
    DocumentClassification,
)


def make_document(**overrides: object) -> Document:
    values = {
        "document_id": "document-1",
        "name": "R6618 TDS",
        "source_url": "https://third-party.test/r6618.pdf",
        "hosting_domain": "third-party.test",
    }
    values.update(overrides)
    return Document(**values)


def test_domain_alone_never_proves_manufacturer() -> None:
    result = classify_company(CompanyVerification(official_domain_verified=True))

    assert result.classification is CompanyClassification.UNKNOWN


def test_explicit_manufacturing_without_human_threshold_is_probable() -> None:
    result = classify_company(
        CompanyVerification(
            explicit_manufacturing_evidence=True,
            primary_manufacturing_evidence=True,
            official_domain_verified=True,
            manufacturer_independent_threshold_met=None,
        )
    )

    assert result.classification is CompanyClassification.PROBABLE_MANUFACTURER


def test_verified_manufacturer_requires_every_gate() -> None:
    result = classify_company(
        CompanyVerification(
            explicit_manufacturing_evidence=True,
            primary_manufacturing_evidence=True,
            official_domain_verified=True,
            manufacturer_independent_threshold_met=True,
        )
    )

    assert result.classification is CompanyClassification.VERIFIED_MANUFACTURER


def test_false_independent_threshold_never_verifies_manufacturer() -> None:
    result = classify_company(
        CompanyVerification(
            explicit_manufacturing_evidence=True,
            primary_manufacturing_evidence=True,
            official_domain_verified=True,
            manufacturer_independent_threshold_met=False,
        )
    )

    assert result.classification is CompanyClassification.PROBABLE_MANUFACTURER
    assert result.classification is not CompanyClassification.VERIFIED_MANUFACTURER


def test_explicit_intermediary_without_manufacturing_is_trader() -> None:
    result = classify_company(CompanyVerification(explicit_trader_evidence=True))

    assert result.classification is CompanyClassification.TRADER


def test_unresolved_contradiction_forces_unknown() -> None:
    result = classify_company(
        CompanyVerification(
            explicit_manufacturing_evidence=True,
            primary_manufacturing_evidence=True,
            official_domain_verified=True,
            manufacturer_independent_threshold_met=True,
            unresolved_relevant_contradiction=True,
        )
    )

    assert result.classification is CompanyClassification.UNKNOWN


def test_distributor_threshold_controls_verified_level() -> None:
    probable = classify_company(
        CompanyVerification(explicit_distribution_evidence=True)
    )
    verified = classify_company(
        CompanyVerification(
            explicit_distribution_evidence=True,
            distributor_threshold_met=True,
        )
    )

    assert probable.classification is CompanyClassification.PROBABLE_DISTRIBUTOR
    assert verified.classification is CompanyClassification.VERIFIED_DISTRIBUTOR


def test_professional_third_party_document_is_not_official() -> None:
    result = classify_document(make_document(known_third_party=True))

    assert result.classification is DocumentClassification.THIRD_PARTY


def test_corroborated_precedes_third_party() -> None:
    result = classify_document(
        make_document(known_third_party=True, corroboration_threshold_met=True)
    )

    assert result.classification is DocumentClassification.CORROBORATED


def test_official_document_requires_all_official_gates() -> None:
    incomplete = classify_document(
        make_document(
            official_domain_verified=True,
            manufacturer_identity_consistent=True,
            product_confirmed_by_primary_source=None,
        )
    )
    complete = classify_document(
        make_document(
            official_domain_verified=True,
            manufacturer_identity_consistent=True,
            product_confirmed_by_primary_source=True,
        )
    )

    assert incomplete.classification is DocumentClassification.UNVERIFIED
    assert complete.classification is DocumentClassification.OFFICIAL
