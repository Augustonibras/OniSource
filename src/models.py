from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TypeAlias


UNKNOWN = "UNKNOWN"
TBD = "TBD"
TBD_HUMAN = "TBD_HUMAN"
NOT_EVALUATED = "NOT_EVALUATED"
NOT_APPLICABLE = "NOT_APPLICABLE"

Scalar: TypeAlias = str | int | float | bool


class PropertyStatus(str, Enum):
    EVIDENCED = "EVIDENCED"
    UNKNOWN = "UNKNOWN"


class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CompanyClassification(str, Enum):
    VERIFIED_MANUFACTURER = "VERIFIED_MANUFACTURER"
    PROBABLE_MANUFACTURER = "PROBABLE_MANUFACTURER"
    VERIFIED_DISTRIBUTOR = "VERIFIED_DISTRIBUTOR"
    PROBABLE_DISTRIBUTOR = "PROBABLE_DISTRIBUTOR"
    TRADER = "TRADER"
    UNKNOWN = "UNKNOWN"


class DocumentClassification(str, Enum):
    OFFICIAL = "OFFICIAL"
    CORROBORATED = "CORROBORATED"
    THIRD_PARTY = "THIRD_PARTY"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class Evidence:
    source_url: str
    source_type: str
    document_name: str
    page: int | str
    evidence_excerpt: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.source_url.strip():
            raise ValueError("source_url is required")
        if not self.source_type.strip():
            raise ValueError("source_type is required")
        if not self.evidence_excerpt.strip():
            raise ValueError("evidence_excerpt is required")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")


@dataclass(frozen=True, slots=True)
class Specification:
    name: str
    property_status: PropertyStatus
    value: Scalar = UNKNOWN
    unit: str = UNKNOWN
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    sources_consulted: tuple[str, ...] = field(default_factory=tuple)
    compliance: ComplianceStatus | None = None
    commercial_grade_equivalence: str = NOT_EVALUATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        consulted = list(dict.fromkeys(self.sources_consulted))
        for item in self.evidence:
            if item.source_url not in consulted:
                consulted.append(item.source_url)
        object.__setattr__(self, "sources_consulted", tuple(consulted))

        if not self.name.strip():
            raise ValueError("specification name is required")
        if self.property_status is PropertyStatus.EVIDENCED:
            if self.value == UNKNOWN:
                raise ValueError("EVIDENCED specifications require a value")
            if not self.evidence:
                raise ValueError("EVIDENCED specifications require evidence")
        elif self.value != UNKNOWN:
            raise ValueError("UNKNOWN specifications cannot contain a factual value")

        if (
            self.property_status is PropertyStatus.UNKNOWN
            and self.compliance in {ComplianceStatus.PASS, ComplianceStatus.FAIL}
        ):
            raise ValueError("PASS and FAIL require an evidenced property")


@dataclass(frozen=True, slots=True)
class CompanyVerification:
    classification: CompanyClassification = CompanyClassification.UNKNOWN
    official_domain_verified: bool | None = None
    explicit_manufacturing_evidence: bool = False
    primary_manufacturing_evidence: bool = False
    explicit_distribution_evidence: bool = False
    explicit_trader_evidence: bool = False
    manufacturer_independent_threshold_met: bool | None = None
    distributor_threshold_met: bool | None = None
    ambiguous_evidence: bool = False
    unresolved_relevant_contradiction: bool = False
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_any_evidence(self) -> bool:
        return any(
            (
                self.explicit_manufacturing_evidence,
                self.primary_manufacturing_evidence,
                self.explicit_distribution_evidence,
                self.explicit_trader_evidence,
            )
        )


@dataclass(frozen=True, slots=True)
class Company:
    name: str
    official_domain: str = UNKNOWN
    business_registration_status: str = "NOT_IMPLEMENTED"
    business_registration_number: str = UNKNOWN
    business_registration_source: str = UNKNOWN
    independent_producer_evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    independent_distributor_evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    verification: CompanyVerification = field(default_factory=CompanyVerification)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("company name is required")
        object.__setattr__(
            self, "independent_producer_evidence", tuple(self.independent_producer_evidence)
        )
        object.__setattr__(
            self,
            "independent_distributor_evidence",
            tuple(self.independent_distributor_evidence),
        )


@dataclass(frozen=True, slots=True)
class Document:
    document_id: str
    name: str
    source_url: str
    claimed_manufacturer: str = UNKNOWN
    hosting_domain: str = UNKNOWN
    official_domain_verified: bool | None = None
    manufacturer_identity_consistent: bool | None = None
    product_confirmed_by_primary_source: bool | None = None
    corroboration_threshold_met: bool | None = None
    known_third_party: bool = False
    classification: DocumentClassification = DocumentClassification.UNVERIFIED
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.name.strip() or not self.source_url.strip():
            raise ValueError("document_id, name and source_url are required")
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True, slots=True)
class CandidateProduct:
    candidate_id: str
    name: str
    company: Company
    discovered_by_query_ids: tuple[str, ...] = field(default_factory=tuple)
    product_page: str = UNKNOWN
    tds_documents: tuple[Document, ...] = field(default_factory=tuple)
    specifications: tuple[Specification, ...] = field(default_factory=tuple)
    applications: tuple[Specification, ...] = field(default_factory=tuple)
    source_urls: tuple[str, ...] = field(default_factory=tuple)
    technical_match: Scalar = TBD
    evidence_confidence: Scalar = TBD_HUMAN
    brazil_import_viability: str = NOT_EVALUATED
    commercial_fit: str = NOT_EVALUATED

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.name.strip():
            raise ValueError("candidate_id and name are required")
        object.__setattr__(self, "discovered_by_query_ids", tuple(self.discovered_by_query_ids))
        object.__setattr__(self, "tds_documents", tuple(self.tds_documents))
        object.__setattr__(self, "specifications", tuple(self.specifications))
        object.__setattr__(self, "applications", tuple(self.applications))
        object.__setattr__(self, "source_urls", tuple(dict.fromkeys(self.source_urls)))


@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    queries_generated: int = 0
    search_results_found: int = 0
    unique_urls: int = 0
    fetch_attempted: int = 0
    fetch_success: int = 0
    fetch_blocked: int = 0
    fetch_timeout: int = 0
    fetch_form_required: int = 0
    fetch_js_required: int = 0
    pdf_candidates: int = 0
    pdf_downloaded: int = 0
    pdf_parseable: int = 0
    pdf_scanned: int = 0
    extraction_attempted: int = 0
    extraction_success: int = 0
    candidate_products: int = 0
    verified_candidates: int = 0

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
