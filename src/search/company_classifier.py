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


PROMPT_VERSION = "v1"
DEFAULT_LLM_CACHE_DIR = (
    Path(__file__).resolve().parents[2] / "cache" / "llm_classifier"
)
_CACHE_FIELDS = {"role", "confidence", "citation", "reasoning"}


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    role: CompanyClassification
    confidence: Confidence
    citation: str
    reasoning: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, CompanyClassification):
            raise TypeError("role must be a CompanyClassification")
        if not isinstance(self.confidence, Confidence):
            raise TypeError("confidence must be a Confidence")
        if not isinstance(self.citation, str):
            raise TypeError("citation must be text")
        if not isinstance(self.reasoning, str):
            raise TypeError("reasoning must be text")


class CompanyClassifier(ABC):
    @abstractmethod
    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
    ) -> ClassificationResult:
        """Classify one domain using only the supplied page evidence."""


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return a provider response. No implementation is selected in Phase 0."""


def classify_with_citation_gate(
    classifier: CompanyClassifier,
    domain: str,
    title: str,
    extracted_content: str,
) -> ClassificationResult:
    """Consume a classifier result and enforce the mandatory evidence gate."""

    result = classifier.classify(domain, title, extracted_content)
    if not result.citation.strip():
        return replace(result, role=CompanyClassification.UNKNOWN)
    return result


class RuleBasedCompanyClassifier(CompanyClassifier):
    """Adapter over the existing fixed-rule report implementation."""

    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
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
            "",
            [result],
            extracted_content_by_url={result.url: extracted_content},
        )
        classification = report["results"][0]["domain_classification"]
        detailed_role = classification["detailed_classification"]
        try:
            role = CompanyClassification(detailed_role)
        except ValueError:
            role = CompanyClassification.UNKNOWN
        reason_codes = classification["reason_codes"]
        reasoning = ", ".join(reason_codes) or "NO_CLASSIFICATION_RULE_MATCHED"
        return ClassificationResult(
            role=role,
            confidence=Confidence.LOW,
            citation="",
            reasoning=reasoning,
        )


def build_llm_company_classifier_prompt(
    domain: str,
    title: str,
    extracted_content: str,
) -> str:
    return f"""You classify company roles for an internal sourcing evidence system.

Use only the supplied domain, page title, and extracted page content. Never infer a role from the domain name, site appearance, wording quality, or an unsupported claim. When evidence is missing, ambiguous, or contradictory, return UNKNOWN. A false MANUFACTURER classification is worse than a false negative.

Allowed role values are exactly: VERIFIED_MANUFACTURER, PROBABLE_MANUFACTURER, VERIFIED_DISTRIBUTOR, PROBABLE_DISTRIBUTOR, TRADER, UNKNOWN.
Allowed confidence values are exactly: HIGH, MEDIUM, LOW.

Role guidance:
- MANUFACTURER requires text showing that the company itself produces or operates manufacturing for the relevant product. A generic self-description as a manufacturer is insufficient without production evidence.
- DISTRIBUTOR requires text showing distribution or resale of products.
- TRADER requires text showing trading, importing, exporting, or commercial intermediation without supported own production.
- VERIFIED roles require explicit corroborating evidence in the supplied content; otherwise use the corresponding PROBABLE role or UNKNOWN.
- If the page is a report, news article, association, directory, marketplace, or data platform rather than the classified company's own page, return UNKNOWN.

Evidence rules:
- citation must be a literal, contiguous excerpt copied exactly from extracted_content.
- Do not use the domain or title as the citation.
- Choose the shortest excerpt that directly supports the role.
- If no literal supporting excerpt exists in extracted_content, set role to UNKNOWN and citation to an empty string.
- reasoning must be short and must not add facts absent from the supplied input.

Return exactly one JSON object with no Markdown, commentary, or additional keys:
{{"role":"UNKNOWN","confidence":"LOW","citation":"","reasoning":"short evidence-based reason"}}

domain:
{domain}

title:
{title}

extracted_content:
{extracted_content}
"""


def llm_cache_key(
    domain: str,
    title: str,
    extracted_content: str,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    serialized = json.dumps(
        [domain, title, extracted_content, prompt_version],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def read_llm_cache(
    cache_dir: str | Path,
    key: str,
) -> dict[str, object] | None:
    path = Path(cache_dir) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid LLM classifier cache entry: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"LLM classifier cache entry must be an object: {path}")
    return payload


def write_llm_cache(
    cache_dir: str | Path,
    key: str,
    response: Mapping[str, object],
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


class LLMCompanyClassifier(CompanyClassifier):
    """Cache-only LLM classifier skeleton; live provider calls are disabled."""

    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        provider: LLMProvider | None,
        cache_dir: str | Path = DEFAULT_LLM_CACHE_DIR,
    ) -> None:
        self.provider = provider
        self.cache_dir = Path(cache_dir)

    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
    ) -> ClassificationResult:
        prompt = build_llm_company_classifier_prompt(
            domain,
            title,
            extracted_content,
        )
        key = llm_cache_key(
            domain,
            title,
            extracted_content,
            self.prompt_version,
        )
        cached_response = read_llm_cache(self.cache_dir, key)
        if cached_response is None:
            raise NotImplementedError("LLM provider not configured")
        return self._parse_cached_response(
            cached_response,
            extracted_content=extracted_content,
            prompt=prompt,
        )

    @staticmethod
    def _parse_cached_response(
        response: Mapping[str, object],
        *,
        extracted_content: str,
        prompt: str,
    ) -> ClassificationResult:
        del prompt
        if set(response) != _CACHE_FIELDS:
            raise ValueError("Cached LLM response must contain exactly four fields")
        try:
            role = CompanyClassification(response["role"])
            confidence = Confidence(response["confidence"])
        except (TypeError, ValueError) as error:
            raise ValueError("Cached LLM response contains an unsupported enum") from error
        citation = response["citation"]
        reasoning = response["reasoning"]
        if not isinstance(citation, str) or not isinstance(reasoning, str):
            raise ValueError("Cached LLM citation and reasoning must be text")
        if citation and citation not in extracted_content:
            raise ValueError("Cached LLM citation is not literal extracted content")
        return ClassificationResult(
            role=role,
            confidence=confidence,
            citation=citation,
            reasoning=reasoning,
        )
