from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Mapping

from src.models import CompanyClassification

from .company_evaluation import build_company_classification_report
from .models import SearchResult


PROMPT_VERSION = "v2"
MAX_CONTENT_CHARS = 12_000
DEFAULT_LLM_CACHE_DIR = (
    Path(__file__).resolve().parents[2] / "cache" / "llm_classifier"
)
LLM_FAILURE_REASONS = (
    "NO_CITATION",
    "CITATION_NOT_FOUND",
    "INVALID_RESPONSE",
)
_CACHE_FIELDS = {"role", "confidence", "citation", "reasoning"}
_ON_MISS_MODES = {"raise", "dry_run"}
_INVALID_CACHED_RESPONSE = object()


class SupplierRole(str, Enum):
    MANUFACTURER = "MANUFACTURER"
    DISTRIBUTOR = "DISTRIBUTOR"
    TRADER = "TRADER"
    MARKETPLACE_OR_DIRECTORY = "MARKETPLACE_OR_DIRECTORY"
    NOT_A_SUPPLIER = "NOT_A_SUPPLIER"
    NOT_A_COMPANY = "NOT_A_COMPANY"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    role: SupplierRole
    confidence: Confidence
    citation: str
    reasoning: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, SupplierRole):
            raise TypeError("role must be a SupplierRole")
        if not isinstance(self.confidence, Confidence):
            raise TypeError("confidence must be a Confidence")
        if not isinstance(self.citation, str):
            raise TypeError("citation must be text")
        if not isinstance(self.reasoning, str):
            raise TypeError("reasoning must be text")


class CompanyClassifier(ABC):
    requires_citation: bool

    @abstractmethod
    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
        product_context: str,
    ) -> ClassificationResult:
        """Classify one domain relative to the supplied product context."""


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return a provider response. No implementation is selected in Phase 0."""


def classify_with_citation_gate(
    classifier: CompanyClassifier,
    domain: str,
    title: str,
    extracted_content: str,
    product_context: str,
) -> ClassificationResult:
    """Consume a result and apply the citation gate only when required."""

    result = classifier.classify(
        domain,
        title,
        extracted_content,
        product_context,
    )
    if classifier.requires_citation and not result.citation.strip():
        return replace(
            result,
            role=SupplierRole.UNKNOWN,
            reasoning="NO_CITATION",
        )
    return result


_RULE_ROLE_MAP = {
    CompanyClassification.VERIFIED_MANUFACTURER.value: SupplierRole.MANUFACTURER,
    CompanyClassification.PROBABLE_MANUFACTURER.value: SupplierRole.MANUFACTURER,
    CompanyClassification.VERIFIED_DISTRIBUTOR.value: SupplierRole.DISTRIBUTOR,
    CompanyClassification.PROBABLE_DISTRIBUTOR.value: SupplierRole.DISTRIBUTOR,
    CompanyClassification.TRADER.value: SupplierRole.TRADER,
    CompanyClassification.UNKNOWN.value: SupplierRole.UNKNOWN,
    "MANUFACTURER": SupplierRole.MANUFACTURER,
    "DISTRIBUTOR": SupplierRole.DISTRIBUTOR,
    "MARKETPLACE": SupplierRole.MARKETPLACE_OR_DIRECTORY,
    "NOT_A_COMPANY": SupplierRole.NOT_A_COMPANY,
}


def rule_role_to_supplier_role(
    rule_role: CompanyClassification | str,
) -> SupplierRole:
    """Map the fixed-rule vocabulary explicitly; unmapped values stay UNKNOWN."""

    value = rule_role.value if isinstance(rule_role, CompanyClassification) else rule_role
    if not isinstance(value, str):
        return SupplierRole.UNKNOWN
    return _RULE_ROLE_MAP.get(value, SupplierRole.UNKNOWN)


class RuleBasedCompanyClassifier(CompanyClassifier):
    """Adapter over the existing fixed-rule report implementation."""

    requires_citation = False

    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
        product_context: str,
    ) -> ClassificationResult:
        normalized_domain = domain.strip().removeprefix("https://").removeprefix(
            "http://"
        )
        normalized_domain = normalized_domain.strip("/")
        result = SearchResult(
            url=f"https://{normalized_domain}/",
            title=title,
            snippet="",
            content=extracted_content,
            raw_score=0.0,
            provider="rule_based",
            query="rule_based_company_classification",
            retrieved_at="1970-01-01T00:00:00Z",
        )
        report = build_company_classification_report(
            product_context,
            [result],
            extracted_content_by_url={result.url: extracted_content},
        )
        classification = report["results"][0]["domain_classification"]
        role = rule_role_to_supplier_role(
            classification["detailed_classification"]
        )
        reason_codes = classification["reason_codes"]
        reasoning = ", ".join(reason_codes) or "NO_CLASSIFICATION_RULE_MATCHED"
        return ClassificationResult(
            role=role,
            confidence=Confidence.LOW,
            citation="",
            reasoning=reasoning,
        )


def truncate_extracted_content(extracted_content: str) -> str:
    return extracted_content[:MAX_CONTENT_CHARS]


def build_llm_company_classifier_prompt(
    domain: str,
    title: str,
    extracted_content: str,
    product_context: str,
) -> str:
    truncated_content = truncate_extracted_content(extracted_content)
    return f"""You classify the role of an entity relative to a specific product for an internal sourcing evidence system.

Use only the supplied domain, page title, product context, and extracted page content. The classification must always be relative to product_context. Never infer a role from the domain name, site appearance, wording quality, or an unsupported claim. When evidence is missing, ambiguous, or contradictory, return UNKNOWN. A false MANUFACTURER classification is worse than a false negative.

Allowed role values are exactly: MANUFACTURER, DISTRIBUTOR, TRADER, MARKETPLACE_OR_DIRECTORY, NOT_A_SUPPLIER, NOT_A_COMPANY, UNCERTAIN, UNKNOWN.
Allowed confidence values are exactly: HIGH, MEDIUM, LOW.

Class definitions:
- MANUFACTURER: the company itself produces or operates manufacturing for the product in product_context, supported by production evidence beyond a generic self-description.
- DISTRIBUTOR: the company distributes or resells the product in product_context without supported evidence that it manufactures that product itself.
- TRADER: the company trades, imports, exports, or intermediates the product in product_context without supported own production.
- MARKETPLACE_OR_DIRECTORY: the page lists multiple sellers, suppliers, companies, or trade records as a marketplace, directory, or data platform rather than representing one supplier.
- NOT_A_SUPPLIER: the entity is a company, but the supplied evidence shows that it does not sell or supply the product in product_context.
- NOT_A_COMPANY: the page is a news portal, market report, government body, association, or other non-company information source.
- UNCERTAIN: the evidence supports that this is a potentially relevant company, but its product-relative commercial role remains conflicting or cannot be separated between manufacturer, distributor, and trader.
- UNKNOWN: the supplied evidence is absent or insufficient to establish that the entity is relevant to the product or to assign any other class.

Evidence rules:
- citation must be a literal, contiguous excerpt from extracted_content; whitespace may be normalized, but words and punctuation must not be changed.
- Do not use the domain or title as the citation.
- Choose the shortest excerpt that directly supports the role.
- If no supporting excerpt exists in extracted_content, set role to UNKNOWN and citation to an empty string.
- reasoning must be short and must not add facts absent from the supplied input.

Return exactly one JSON object with no Markdown, commentary, or additional keys:
{{"role":"UNKNOWN","confidence":"LOW","citation":"","reasoning":"short evidence-based reason"}}

domain:
{domain}

title:
{title}

product_context:
{product_context}

extracted_content:
{truncated_content}
"""


def llm_cache_key(
    domain: str,
    title: str,
    extracted_content: str,
    product_context: str,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    truncated_content = truncate_extracted_content(extracted_content)
    serialized = json.dumps(
        [domain, title, truncated_content, product_context, prompt_version],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def read_llm_cache(
    cache_dir: str | Path,
    key: str,
) -> object | None:
    path = Path(cache_dir) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except json.JSONDecodeError:
        return _INVALID_CACHED_RESPONSE
    except OSError as error:
        raise ValueError(f"Could not read LLM classifier cache entry: {path}") from error


def write_llm_cache(
    cache_dir: str | Path,
    key: str,
    response: object,
) -> Path:
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.json"
    temporary_path = directory / f".{key}.tmp"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as cache_file:
            json.dump(response, cache_file, ensure_ascii=False, indent=2, sort_keys=True)
            cache_file.write("\n")
        temporary_path.replace(path)
    except OSError as error:
        raise ValueError(f"Could not write LLM classifier cache entry: {path}") from error
    return path


def write_pending_prompt(
    cache_dir: str | Path,
    key: str,
    prompt: str,
) -> Path:
    pending_dir = Path(cache_dir) / "_pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{key}.prompt.txt"
    temporary_path = pending_dir / f".{key}.tmp"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as prompt_file:
            prompt_file.write(prompt)
        temporary_path.replace(path)
    except OSError as error:
        raise ValueError(f"Could not write pending LLM prompt: {path}") from error
    return path


def _normalized_whitespace(value: str) -> str:
    return " ".join(value.split())


class LLMCompanyClassifier(CompanyClassifier):
    """Cache-only LLM classifier skeleton; live provider calls are disabled."""

    requires_citation = True
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        provider: LLMProvider | None,
        cache_dir: str | Path = DEFAULT_LLM_CACHE_DIR,
        *,
        on_miss: str = "raise",
    ) -> None:
        if on_miss not in _ON_MISS_MODES:
            raise ValueError("on_miss must be 'raise' or 'dry_run'")
        self.provider = provider
        self.cache_dir = Path(cache_dir)
        self.on_miss = on_miss
        self._failure_counts = {reason: 0 for reason in LLM_FAILURE_REASONS}
        self._planned_keys: set[str] = set()
        self._planned_calls = 0
        self._total_prompt_characters = 0

    @property
    def execution_metrics(self) -> dict[str, object]:
        return {
            "provider_calls_planned": self._planned_calls,
            "total_prompt_characters": self._total_prompt_characters,
            "estimated_input_tokens": self._total_prompt_characters / 4,
            "token_estimation_method": "characters / 4",
            "failure_counts": dict(self._failure_counts),
        }

    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
        product_context: str,
    ) -> ClassificationResult:
        truncated_content = truncate_extracted_content(extracted_content)
        prompt = build_llm_company_classifier_prompt(
            domain,
            title,
            truncated_content,
            product_context,
        )
        key = llm_cache_key(
            domain,
            title,
            truncated_content,
            product_context,
            self.prompt_version,
        )
        cached_response = read_llm_cache(self.cache_dir, key)
        if cached_response is not None:
            return self._parse_response(
                cached_response,
                extracted_content=truncated_content,
            )
        if self.on_miss == "raise":
            raise NotImplementedError("LLM provider not configured")
        if key not in self._planned_keys:
            self._planned_keys.add(key)
            write_pending_prompt(self.cache_dir, key, prompt)
            self._planned_calls += 1
            self._total_prompt_characters += len(prompt)
        return ClassificationResult(
            role=SupplierRole.UNKNOWN,
            confidence=Confidence.LOW,
            citation="",
            reasoning="CACHE_MISS_DRY_RUN",
        )

    def _failure_result(self, reason: str) -> ClassificationResult:
        self._failure_counts[reason] += 1
        return ClassificationResult(
            role=SupplierRole.UNKNOWN,
            confidence=Confidence.LOW,
            citation="",
            reasoning=reason,
        )

    def _parse_response(
        self,
        response: object,
        *,
        extracted_content: str,
    ) -> ClassificationResult:
        if response is _INVALID_CACHED_RESPONSE:
            return self._failure_result("INVALID_RESPONSE")
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return self._failure_result("INVALID_RESPONSE")
        if not isinstance(response, Mapping) or set(response) != _CACHE_FIELDS:
            return self._failure_result("INVALID_RESPONSE")
        try:
            role = SupplierRole(response["role"])
            confidence = Confidence(response["confidence"])
        except (TypeError, ValueError):
            return self._failure_result("INVALID_RESPONSE")
        citation = response["citation"]
        reasoning = response["reasoning"]
        if not isinstance(citation, str) or not isinstance(reasoning, str):
            return self._failure_result("INVALID_RESPONSE")
        if not citation.strip():
            return self._failure_result("NO_CITATION")
        normalized_citation = _normalized_whitespace(citation)
        normalized_content = _normalized_whitespace(extracted_content)
        if normalized_citation not in normalized_content:
            return self._failure_result("CITATION_NOT_FOUND")
        return ClassificationResult(
            role=role,
            confidence=confidence,
            citation=citation,
            reasoning=reasoning,
        )
