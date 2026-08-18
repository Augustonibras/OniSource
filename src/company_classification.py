from __future__ import annotations

from dataclasses import replace

from src.models import CompanyClassification, CompanyVerification


def classify_company(verification: CompanyVerification) -> CompanyVerification:
    if (
        not verification.has_any_evidence
        or verification.ambiguous_evidence
        or verification.unresolved_relevant_contradiction
    ):
        return replace(
            verification,
            classification=CompanyClassification.UNKNOWN,
            reason_codes=("INSUFFICIENT_AMBIGUOUS_OR_CONFLICTING_EVIDENCE",),
        )

    if (
        verification.explicit_trader_evidence
        and not verification.explicit_manufacturing_evidence
    ):
        return replace(
            verification,
            classification=CompanyClassification.TRADER,
            reason_codes=("EXPLICIT_INTERMEDIARY_WITHOUT_MANUFACTURING_EVIDENCE",),
        )

    if verification.explicit_manufacturing_evidence:
        verified = all(
            (
                verification.official_domain_verified is True,
                verification.primary_manufacturing_evidence,
                verification.manufacturer_independent_threshold_met is True,
            )
        )
        return replace(
            verification,
            classification=(
                CompanyClassification.VERIFIED_MANUFACTURER
                if verified
                else CompanyClassification.PROBABLE_MANUFACTURER
            ),
            reason_codes=(
                "VERIFIED_MANUFACTURER_GATES_MET"
                if verified
                else "MANUFACTURING_EXPLICIT_VERIFICATION_GATES_INCOMPLETE",
            ),
        )

    if verification.explicit_distribution_evidence:
        verified = verification.distributor_threshold_met is True
        return replace(
            verification,
            classification=(
                CompanyClassification.VERIFIED_DISTRIBUTOR
                if verified
                else CompanyClassification.PROBABLE_DISTRIBUTOR
            ),
            reason_codes=(
                "VERIFIED_DISTRIBUTOR_GATE_MET"
                if verified
                else "DISTRIBUTION_EXPLICIT_VERIFICATION_GATE_INCOMPLETE",
            ),
        )

    return replace(
        verification,
        classification=CompanyClassification.UNKNOWN,
        reason_codes=("NO_CLASSIFICATION_RULE_MATCHED",),
    )
