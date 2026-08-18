from __future__ import annotations

from dataclasses import replace

from src.models import Document, DocumentClassification


def classify_document(document: Document) -> Document:
    if all(
        (
            document.official_domain_verified is True,
            document.manufacturer_identity_consistent is True,
            document.product_confirmed_by_primary_source is True,
        )
    ):
        classification = DocumentClassification.OFFICIAL
    elif document.corroboration_threshold_met is True:
        classification = DocumentClassification.CORROBORATED
    elif document.known_third_party:
        classification = DocumentClassification.THIRD_PARTY
    else:
        classification = DocumentClassification.UNVERIFIED

    return replace(document, classification=classification)
