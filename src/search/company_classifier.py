from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from src.models import CompanyClassification

from .company_evaluation import build_company_classification_report
from .models import SearchResult


PROMPT_VERSION = "v7"
MAX_CONTENT_CHARS = 40_000
CONTENT_BUDGET_POLICY = "per_page_equal_quota_redistribute_v1"
DEFAULT_LLM_CACHE_DIR = (
    Path(__file__).resolve().parents[2] / "cache" / "llm_classifier"
)
LLM_FAILURE_REASONS = (
    "NO_CITATION",
    "CITATION_NOT_FOUND",
    "INVALID_RESPONSE",
    "EMPTY_RESPONSE",
)
_CACHE_FIELDS = {"role", "confidence", "citation", "reasoning", "needs_review"}
_ON_MISS_MODES = {"raise", "dry_run", "live"}
_PROVIDER_CACHE_FORMAT = "raw_llm_provider_response_v1"
_INVALID_CACHED_RESPONSE = object()
PAGE_BREAK = "\n--- PAGE BREAK ---\n"
TRUNCATED_MARKER = "[TRUNCATED]"


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
    needs_review: bool = False
    evidence_truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.role, SupplierRole):
            raise TypeError("role must be a SupplierRole")
        if not isinstance(self.confidence, Confidence):
            raise TypeError("confidence must be a Confidence")
        if not isinstance(self.citation, str):
            raise TypeError("citation must be text")
        if not isinstance(self.reasoning, str):
            raise TypeError("reasoning must be text")
        if not isinstance(self.needs_review, bool):
            raise TypeError("needs_review must be boolean")
        if not isinstance(self.evidence_truncated, bool):
            raise TypeError("evidence_truncated must be boolean")
        if self.confidence is Confidence.LOW and not self.needs_review:
            object.__setattr__(self, "needs_review", True)


class CompanyClassifier(ABC):
    requires_citation: bool

    @abstractmethod
    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
        product_context: str,
        *,
        marketplace_signal: bool = False,
        marketplace_signal_reason: str = "",
        noise_signal: bool = False,
        noise_signal_reason: str = "",
    ) -> ClassificationResult:
        """Classify one domain relative to the supplied product context."""


@dataclass(frozen=True, slots=True)
class DomainClassificationInput:
    domain: str
    title: str
    extracted_content: str
    page_count: int
    source_urls: tuple[str, ...]
    marketplace_signal: bool = False
    marketplace_signal_reasons: tuple[str, ...] = ()
    noise_signal: bool = False
    noise_signal_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BudgetedEvidence:
    content: str
    evidence_truncated: bool
    page_allocations: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LLMTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    thoughts_tokens: int = 0
    finish_reason: str = ""
    empty_response: bool = False

    def __post_init__(self) -> None:
        for field_value in (
            self.input_tokens,
            self.output_tokens,
            self.total_tokens,
            self.thoughts_tokens,
        ):
            if (
                isinstance(field_value, bool)
                or not isinstance(field_value, int)
                or field_value < 0
            ):
                raise ValueError("LLM token usage must contain non-negative integers")
        if not isinstance(self.finish_reason, str):
            raise TypeError("finish_reason must be text")
        if not isinstance(self.empty_response, bool):
            raise TypeError("empty_response must be boolean")


def normalize_classifier_domain(value: str) -> str:
    """Normalize a host without collapsing www or any other subdomain."""

    candidate = value.strip()
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    if not parsed.hostname:
        raise ValueError("domain must contain a hostname")
    return parsed.hostname.casefold()


def group_extracted_pages_by_domain(
    results: Iterable[SearchResult],
    extracted_content_by_url: Mapping[str, str],
) -> tuple[DomainClassificationInput, ...]:
    """Build one classification input per domain in first-appearance order."""

    grouped: dict[str, dict[str, object]] = {}
    seen_urls: set[str] = set()
    for result in results:
        if result.url in seen_urls or result.url not in extracted_content_by_url:
            continue
        seen_urls.add(result.url)
        domain = normalize_classifier_domain(result.url)
        if domain not in grouped:
            grouped[domain] = {
                "title": result.title,
                "contents": [],
                "source_urls": [],
                "marketplace_signal_reasons": [],
                "noise_signal_reasons": [],
            }
        contents = grouped[domain]["contents"]
        source_urls = grouped[domain]["source_urls"]
        if not isinstance(contents, list) or not isinstance(source_urls, list):
            raise TypeError("domain aggregation state must contain lists")
        contents.append(extracted_content_by_url[result.url])
        source_urls.append(result.url)
        marketplace_reasons = grouped[domain]["marketplace_signal_reasons"]
        noise_reasons = grouped[domain]["noise_signal_reasons"]
        if not isinstance(marketplace_reasons, list) or not isinstance(
            noise_reasons, list
        ):
            raise TypeError("domain signal aggregation state must contain lists")
        if (
            result.marketplace_signal_reason
            and result.marketplace_signal_reason not in marketplace_reasons
        ):
            marketplace_reasons.append(result.marketplace_signal_reason)
        if result.noise_signal_reason and result.noise_signal_reason not in noise_reasons:
            noise_reasons.append(result.noise_signal_reason)

    aggregated: list[DomainClassificationInput] = []
    for domain, values in grouped.items():
        contents = values["contents"]
        source_urls = values["source_urls"]
        marketplace_reasons = values["marketplace_signal_reasons"]
        noise_reasons = values["noise_signal_reasons"]
        title = values["title"]
        if (
            not isinstance(contents, list)
            or not all(isinstance(item, str) for item in contents)
            or not isinstance(source_urls, list)
            or not all(isinstance(item, str) for item in source_urls)
            or not isinstance(marketplace_reasons, list)
            or not all(isinstance(item, str) for item in marketplace_reasons)
            or not isinstance(noise_reasons, list)
            or not all(isinstance(item, str) for item in noise_reasons)
            or not isinstance(title, str)
        ):
            raise TypeError("domain aggregation state is malformed")
        aggregated.append(
            DomainClassificationInput(
                domain=domain,
                title=title,
                extracted_content=PAGE_BREAK.join(contents),
                page_count=len(source_urls),
                source_urls=tuple(source_urls),
                marketplace_signal=bool(marketplace_reasons),
                marketplace_signal_reasons=tuple(marketplace_reasons),
                noise_signal=bool(noise_reasons),
                noise_signal_reasons=tuple(noise_reasons),
            )
        )
    return tuple(aggregated)


class LLMProvider(ABC):
    provider_name = "unconfigured_llm"
    model = "unconfigured_llm"

    @abstractmethod
    def complete(self, prompt: str) -> object:
        """Return the raw provider response without interpreting model output."""

    def parse_response(self, raw_response: object) -> tuple[object, LLMTokenUsage]:
        """Normalize model output after the caller has persisted the raw response."""

        return raw_response, LLMTokenUsage()

    @property
    def execution_metrics(self) -> dict[str, object]:
        return {}


def classify_with_citation_gate(
    classifier: CompanyClassifier,
    domain: str,
    title: str,
    extracted_content: str,
    product_context: str,
    *,
    marketplace_signal: bool = False,
    marketplace_signal_reason: str = "",
    noise_signal: bool = False,
    noise_signal_reason: str = "",
) -> ClassificationResult:
    """Consume a result and apply the citation gate only when required."""

    result = classifier.classify(
        domain,
        title,
        extracted_content,
        product_context,
        marketplace_signal=marketplace_signal,
        marketplace_signal_reason=marketplace_signal_reason,
        noise_signal=noise_signal,
        noise_signal_reason=noise_signal_reason,
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
        *,
        marketplace_signal: bool = False,
        marketplace_signal_reason: str = "",
        noise_signal: bool = False,
        noise_signal_reason: str = "",
    ) -> ClassificationResult:
        normalized_domain = normalize_classifier_domain(domain)
        result = SearchResult(
            url=f"https://{normalized_domain}/",
            title=title,
            snippet="",
            content=extracted_content,
            raw_score=0.0,
            provider="rule_based",
            query="rule_based_company_classification",
            retrieved_at="1970-01-01T00:00:00Z",
            marketplace_signal=marketplace_signal,
            marketplace_signal_reason=marketplace_signal_reason,
            noise_signal=noise_signal,
            noise_signal_reason=noise_signal_reason,
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


def _allocate_page_characters(page_lengths: tuple[int, ...]) -> tuple[int, ...]:
    allocations = [0] * len(page_lengths)
    remaining_budget = MAX_CONTENT_CHARS
    active = list(range(len(page_lengths)))
    while active:
        quota = remaining_budget // len(active)
        fitting = [index for index in active if page_lengths[index] <= quota]
        if fitting:
            for index in fitting:
                allocations[index] = page_lengths[index]
                remaining_budget -= page_lengths[index]
            fitting_set = set(fitting)
            active = [index for index in active if index not in fitting_set]
            continue

        for index in active:
            allocations[index] = quota
        remainder = remaining_budget - quota * len(active)
        for index in active[:remainder]:
            allocations[index] += 1
        remaining_budget = 0
        break
    return tuple(allocations)


def budget_extracted_content(extracted_content: str) -> BudgetedEvidence:
    pages = tuple(extracted_content.split(PAGE_BREAK))
    allocations = _allocate_page_characters(tuple(len(page) for page in pages))
    truncated_pages: list[str] = []
    evidence_truncated = False
    for page, allocation in zip(pages, allocations):
        page_was_truncated = allocation < len(page)
        truncated_page = page[:allocation]
        if page_was_truncated:
            truncated_page += TRUNCATED_MARKER
            evidence_truncated = True
        truncated_pages.append(truncated_page)
    return BudgetedEvidence(
        content=PAGE_BREAK.join(truncated_pages),
        evidence_truncated=evidence_truncated,
        page_allocations=allocations,
    )


def truncate_extracted_content(extracted_content: str) -> str:
    return budget_extracted_content(extracted_content).content


def _render_llm_company_classifier_prompt(
    normalized_domain: str,
    title: str,
    budgeted_evidence: BudgetedEvidence,
    product_context: str,
    marketplace_signal: bool,
    marketplace_signal_reason: str,
    noise_signal: bool,
    noise_signal_reason: str,
) -> str:
    evidence_truncated = str(budgeted_evidence.evidence_truncated).lower()
    marketplace_signal_text = str(marketplace_signal).lower()
    noise_signal_text = str(noise_signal).lower()
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

Classification unit:
- The task is to classify the entity that owns the domain, using its pages as evidence about that entity.
- A page about a discontinued, sold out, or out-of-line product does not make the entity NOT_A_SUPPLIER; it is evidence about one product, not about the nature of the company.
- An article, blog post, comparison, or ranking published on the company's own site does not make the entity MARKETPLACE_OR_DIRECTORY or NOT_A_COMPANY. Those classes describe the nature of the entity: a marketplace or directory exists to list third parties, while NOT_A_COMPANY is a news outlet, market-research consultancy, government body, or association. A trading company that publishes a ranking remains a trading company.
- When the domain content is predominantly commercial, such as products, quotations, and sales contacts, and only part is editorial, classify according to the commercial content.

Decision rules (apply in this exact order):
1. Selling a third-party brand is decisive. If the entity resells, represents, or acts as an agent for third-party brands, such as "agents for different brands", "we supply Lomon, Taihai, panzhihua", or "LOMON Brand", the role is TRADER without exception, even if the entity also calls itself a manufacturer.
2. Multiple self-declared roles mean TRADER. If the entity describes itself simultaneously as a manufacturer and as a trading company, agent, or distributor, such as "Business Type: Manufacturer, Distributor/Wholesaler, Agent, Trade Company", and there is no own-production proof, the role is TRADER.
3. A production-capacity claim alone is not enough for MANUFACTURER. Claims about operating factories, stated monthly capacity, or being "the largest manufacturer" are self-declarations rather than proof. Use the best-supported role and set needs_review to true.
4. MANUFACTURER requires own-production evidence beyond self-declaration: a described production process, an identified plant with its location, a factory certification, detailed technological capability, or verifiable industrial history.
5. UNCERTAIN is an exception, not the default. Use it only for genuinely conflicting evidence between two specific roles, and name both roles in reasoning. If the entity clearly commercializes the product but the operation type cannot be determined, prefer TRADER over UNCERTAIN: commercializing without proof of production is intermediation by definition.

Review rule:
- needs_review must be true whenever decision rule 3 applies or confidence is LOW; otherwise it may be false.

Evidence rules:
- citation must be a literal, contiguous excerpt from extracted_content; whitespace may be normalized, but words and punctuation must not be changed.
- Do not use the domain or title as the citation.
- For a commercial company role, citation must evidence the entity's commercial activity with the product. It does not need to prove the exact role. A literal institutional sentence showing that the entity commercializes the product is valid.
- For MARKETPLACE_OR_DIRECTORY or NOT_A_COMPANY, citation must evidence the nature of the entity.
- Choose the shortest excerpt that satisfies the applicable citation rule.
- [TRUNCATED] marks the end of a page whose remaining content was omitted by the deterministic per-page budget.
- If no excerpt satisfying the applicable citation rule exists in extracted_content, set role to UNKNOWN and citation to an empty string.
- reasoning must be short and must not add facts absent from the supplied input.
- marketplace_signal and noise_signal are human-configured retrieval hints. They are evidence inputs to consider, not automatic classifications.

Return exactly one JSON object with no Markdown, commentary, or additional keys:
{{"role":"UNKNOWN","confidence":"LOW","citation":"","reasoning":"short evidence-based reason","needs_review":true}}

domain:
{normalized_domain}

title:
{title}

product_context:
{product_context}

evidence_truncated:
{evidence_truncated}

marketplace_signal:
{marketplace_signal_text}

marketplace_signal_reason:
{marketplace_signal_reason}

noise_signal:
{noise_signal_text}

noise_signal_reason:
{noise_signal_reason}

extracted_content:
{budgeted_evidence.content}
"""


def build_llm_company_classifier_prompt(
    domain: str,
    title: str,
    extracted_content: str,
    product_context: str,
    *,
    marketplace_signal: bool = False,
    marketplace_signal_reason: str = "",
    noise_signal: bool = False,
    noise_signal_reason: str = "",
) -> str:
    normalized_domain = normalize_classifier_domain(domain)
    budgeted_evidence = budget_extracted_content(extracted_content)
    return _render_llm_company_classifier_prompt(
        normalized_domain,
        title,
        budgeted_evidence,
        product_context,
        marketplace_signal,
        marketplace_signal_reason,
        noise_signal,
        noise_signal_reason,
    )


def _llm_cache_key_from_budgeted_evidence(
    normalized_domain: str,
    title: str,
    budgeted_evidence: BudgetedEvidence,
    product_context: str,
    prompt_version: str,
    model: str,
    marketplace_signal: bool,
    marketplace_signal_reason: str,
    noise_signal: bool,
    noise_signal_reason: str,
) -> str:
    serialized = json.dumps(
        [
            normalized_domain,
            title,
            budgeted_evidence.content,
            budgeted_evidence.evidence_truncated,
            product_context,
            prompt_version,
            model,
            MAX_CONTENT_CHARS,
            CONTENT_BUDGET_POLICY,
            marketplace_signal,
            marketplace_signal_reason,
            noise_signal,
            noise_signal_reason,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def llm_cache_key(
    domain: str,
    title: str,
    extracted_content: str,
    product_context: str,
    prompt_version: str = PROMPT_VERSION,
    *,
    model: str = LLMProvider.model,
    marketplace_signal: bool = False,
    marketplace_signal_reason: str = "",
    noise_signal: bool = False,
    noise_signal_reason: str = "",
) -> str:
    normalized_domain = normalize_classifier_domain(domain)
    budgeted_evidence = budget_extracted_content(extracted_content)
    return _llm_cache_key_from_budgeted_evidence(
        normalized_domain,
        title,
        budgeted_evidence,
        product_context,
        prompt_version,
        model,
        marketplace_signal,
        marketplace_signal_reason,
        noise_signal,
        noise_signal_reason,
    )


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


def _provider_cache_envelope(
    provider: LLMProvider,
    raw_response: object,
) -> dict[str, object]:
    return {
        "format": _PROVIDER_CACHE_FORMAT,
        "provider": provider.provider_name,
        "model": provider.model,
        "prompt_version": PROMPT_VERSION,
        "raw_response": raw_response,
    }


def _cached_model_response(cached_response: object) -> object:
    if not isinstance(cached_response, Mapping):
        return cached_response
    if cached_response.get("format") != _PROVIDER_CACHE_FORMAT:
        return cached_response
    return cached_response.get("model_response", _INVALID_CACHED_RESPONSE)


def _cached_failure_reason(cached_response: object) -> str | None:
    if not isinstance(cached_response, Mapping):
        return None
    if cached_response.get("format") != _PROVIDER_CACHE_FORMAT:
        return None
    failure_reason = cached_response.get("failure_reason")
    return failure_reason if failure_reason == "EMPTY_RESPONSE" else None


class LLMCompanyClassifier(CompanyClassifier):
    """Evidence classifier with explicit cache-only, dry-run and live modes."""

    requires_citation = True
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        provider: LLMProvider | None,
        cache_dir: str | Path = DEFAULT_LLM_CACHE_DIR,
        *,
        on_miss: str = "raise",
        model: str | None = None,
    ) -> None:
        if on_miss not in _ON_MISS_MODES:
            raise ValueError("on_miss must be 'raise', 'dry_run' or 'live'")
        self.provider = provider
        self.model = (
            provider.model if provider is not None else (model or LLMProvider.model)
        )
        self.cache_dir = Path(cache_dir)
        self.on_miss = on_miss
        self._failure_counts = {reason: 0 for reason in LLM_FAILURE_REASONS}
        self._planned_keys: set[str] = set()
        self._planned_calls = 0
        self._total_prompt_characters = 0

    @property
    def execution_metrics(self) -> dict[str, object]:
        metrics: dict[str, object] = {
            "provider_calls_planned": self._planned_calls,
            "total_prompt_characters": self._total_prompt_characters,
            "estimated_input_tokens": self._total_prompt_characters / 4,
            "token_estimation_method": "characters / 4",
            "failure_counts": dict(self._failure_counts),
        }
        if self.provider is not None and self.provider.execution_metrics:
            metrics["provider_usage"] = self.provider.execution_metrics
        return metrics

    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
        product_context: str,
        *,
        marketplace_signal: bool = False,
        marketplace_signal_reason: str = "",
        noise_signal: bool = False,
        noise_signal_reason: str = "",
    ) -> ClassificationResult:
        normalized_domain = normalize_classifier_domain(domain)
        budgeted_evidence = budget_extracted_content(extracted_content)
        prompt = _render_llm_company_classifier_prompt(
            normalized_domain,
            title,
            budgeted_evidence,
            product_context,
            marketplace_signal,
            marketplace_signal_reason,
            noise_signal,
            noise_signal_reason,
        )
        key = _llm_cache_key_from_budgeted_evidence(
            normalized_domain,
            title,
            budgeted_evidence,
            product_context,
            self.prompt_version,
            self.model,
            marketplace_signal,
            marketplace_signal_reason,
            noise_signal,
            noise_signal_reason,
        )
        cached_response = read_llm_cache(self.cache_dir, key)
        if cached_response is not None:
            cached_failure_reason = _cached_failure_reason(cached_response)
            if cached_failure_reason is not None:
                return self._failure_result(
                    cached_failure_reason,
                    evidence_truncated=budgeted_evidence.evidence_truncated,
                )
            return self._parse_response(
                _cached_model_response(cached_response),
                extracted_content=budgeted_evidence.content,
                evidence_truncated=budgeted_evidence.evidence_truncated,
            )
        if self.on_miss == "raise":
            raise NotImplementedError("LLM provider not configured")
        if self.on_miss == "dry_run" and key not in self._planned_keys:
            self._planned_keys.add(key)
            write_pending_prompt(self.cache_dir, key, prompt)
            self._planned_calls += 1
            self._total_prompt_characters += len(prompt)
        if self.on_miss == "dry_run":
            return ClassificationResult(
                role=SupplierRole.UNKNOWN,
                confidence=Confidence.LOW,
                citation="",
                reasoning="CACHE_MISS_DRY_RUN",
                evidence_truncated=budgeted_evidence.evidence_truncated,
            )

        if self.provider is None:
            raise NotImplementedError("LLM provider not configured")
        raw_response = self.provider.complete(prompt)
        cache_envelope = _provider_cache_envelope(self.provider, raw_response)
        write_llm_cache(self.cache_dir, key, cache_envelope)
        try:
            model_response, token_usage = self.provider.parse_response(raw_response)
        except (TypeError, ValueError):
            return self._failure_result(
                "INVALID_RESPONSE",
                evidence_truncated=budgeted_evidence.evidence_truncated,
            )
        cache_envelope["model_response"] = model_response
        cache_envelope["usage_metadata"] = {
            "input_tokens": token_usage.input_tokens,
            "output_tokens": token_usage.output_tokens,
            "thoughts_tokens": token_usage.thoughts_tokens,
            "total_tokens": token_usage.total_tokens,
            "finish_reason": token_usage.finish_reason,
            "empty_response": token_usage.empty_response,
        }
        if token_usage.empty_response:
            cache_envelope["failure_reason"] = "EMPTY_RESPONSE"
        write_llm_cache(self.cache_dir, key, cache_envelope)
        if token_usage.empty_response:
            return self._failure_result(
                "EMPTY_RESPONSE",
                evidence_truncated=budgeted_evidence.evidence_truncated,
            )
        return self._parse_response(
            model_response,
            extracted_content=budgeted_evidence.content,
            evidence_truncated=budgeted_evidence.evidence_truncated,
        )

    def _failure_result(
        self,
        reason: str,
        *,
        evidence_truncated: bool,
    ) -> ClassificationResult:
        self._failure_counts[reason] += 1
        return ClassificationResult(
            role=SupplierRole.UNKNOWN,
            confidence=Confidence.LOW,
            citation="",
            reasoning=reason,
            evidence_truncated=evidence_truncated,
        )

    def _parse_response(
        self,
        response: object,
        *,
        extracted_content: str,
        evidence_truncated: bool,
    ) -> ClassificationResult:
        if response is _INVALID_CACHED_RESPONSE:
            return self._failure_result(
                "INVALID_RESPONSE",
                evidence_truncated=evidence_truncated,
            )
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return self._failure_result(
                    "INVALID_RESPONSE",
                    evidence_truncated=evidence_truncated,
                )
        if not isinstance(response, Mapping) or set(response) != _CACHE_FIELDS:
            return self._failure_result(
                "INVALID_RESPONSE",
                evidence_truncated=evidence_truncated,
            )
        try:
            role = SupplierRole(response["role"])
            confidence = Confidence(response["confidence"])
        except (TypeError, ValueError):
            return self._failure_result(
                "INVALID_RESPONSE",
                evidence_truncated=evidence_truncated,
            )
        citation = response["citation"]
        reasoning = response["reasoning"]
        needs_review = response["needs_review"]
        if (
            not isinstance(citation, str)
            or not isinstance(reasoning, str)
            or not isinstance(needs_review, bool)
        ):
            return self._failure_result(
                "INVALID_RESPONSE",
                evidence_truncated=evidence_truncated,
            )
        if not citation.strip():
            return self._failure_result(
                "NO_CITATION",
                evidence_truncated=evidence_truncated,
            )
        normalized_citation = _normalized_whitespace(citation)
        normalized_content = _normalized_whitespace(extracted_content)
        if normalized_citation not in normalized_content:
            return self._failure_result(
                "CITATION_NOT_FOUND",
                evidence_truncated=evidence_truncated,
            )
        return ClassificationResult(
            role=role,
            confidence=confidence,
            citation=citation,
            reasoning=reasoning,
            needs_review=needs_review,
            evidence_truncated=evidence_truncated,
        )
