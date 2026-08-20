from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from src.company_classification import classify_company
from src.models import (
    NOT_APPLICABLE,
    UNKNOWN,
    CompanyClassification,
    CompanyVerification,
    Evidence,
)

from .coverage import (
    BenchmarkEntity,
    load_benchmark_entities,
    match_benchmark_entity,
)
from .marketplace import MarketplaceDomainRegistry
from .models import SearchResult


_ROLE_PATTERNS = {
    "explicit_manufacturing_evidence": re.compile(
        r"\b(?:manufacturers?|manufactures?|producers?|produces?)\b|"
        r"\bwe\s+make\b",
        re.IGNORECASE,
    ),
    "explicit_distribution_evidence": re.compile(
        r"\b(?:distributors?|distributes?|distribution|resellers?|resells?)\b",
        re.IGNORECASE,
    ),
    "explicit_trader_evidence": re.compile(
        r"\b(?:traders?|trading|intermediar(?:y|ies))\b",
        re.IGNORECASE,
    ),
}

_DIRECT_DOMAIN_PATTERNS = {
    "explicit_manufacturing_evidence": re.compile(
        r"\bwe\b.{0,80}\b(?:manufacturers?|manufactures?|producers?|produces?|make)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "explicit_distribution_evidence": re.compile(
        r"\bwe\b.{0,80}\b(?:distributors?|distributes?|distribution|resellers?|resells?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "explicit_trader_evidence": re.compile(
        r"\bwe\b.{0,80}\b(?:traders?|trading|intermediar(?:y|ies))\b",
        re.IGNORECASE | re.DOTALL,
    ),
}

_MAX_ENTITY_ROLE_DISTANCE = 160


@dataclass(frozen=True, slots=True)
class _RoleSignal:
    supports: str
    evidence: Evidence
    primary_source: bool


def _target_pattern(name: str) -> re.Pattern[str] | None:
    if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", name.casefold()):
        return None
    tokens = re.findall(r"[^\W_]+", name, flags=re.UNICODE)
    if not tokens:
        return None
    return re.compile(
        r"\b" + r"[^\w]+".join(re.escape(token) for token in tokens) + r"\b",
        re.IGNORECASE,
    )


def _distance(first: re.Match[str], second: re.Match[str]) -> int:
    if first.end() < second.start():
        return second.start() - first.end()
    if second.end() < first.start():
        return first.start() - second.end()
    return 0


def _excerpt(text: str, first: re.Match[str], second: re.Match[str]) -> str:
    start = max(0, min(first.start(), second.start()) - 80)
    end = min(len(text), max(first.end(), second.end()) + 160)
    return text[start:end].strip()


def _direct_excerpt(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 160)
    return text[start:end].strip()


def _retrieved_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _role_signals(
    entity: BenchmarkEntity,
    result: SearchResult,
    matched_by: tuple[str, ...],
    extracted_content: str = "",
) -> tuple[_RoleSignal, ...]:
    target_pattern = _target_pattern(entity.name)
    fragments = (
        ("SEARCH_RESULT_TITLE", result.title),
        ("SEARCH_RESULT_SNIPPET", result.snippet),
        ("SEARCH_RESULT_CONTENT", result.content),
        ("EXTRACTED_CONTENT", extracted_content),
    )
    signals: list[_RoleSignal] = []

    for support, role_pattern in _ROLE_PATTERNS.items():
        best: tuple[int, str, str] | None = None
        if target_pattern is not None:
            for source_type, text in fragments:
                if not text:
                    continue
                target_matches = tuple(target_pattern.finditer(text))
                role_matches = tuple(role_pattern.finditer(text))
                for target_match in target_matches:
                    for role_match in role_matches:
                        distance = _distance(target_match, role_match)
                        if distance > _MAX_ENTITY_ROLE_DISTANCE:
                            continue
                        candidate = (
                            distance,
                            source_type,
                            _excerpt(text, target_match, role_match),
                        )
                        if best is None or candidate[0] < best[0]:
                            best = candidate

        primary_source = "domain" in matched_by and not entity.negative
        if best is None and primary_source:
            direct_pattern = _DIRECT_DOMAIN_PATTERNS[support]
            for source_type, text in fragments:
                if not text:
                    continue
                direct_match = direct_pattern.search(text)
                if direct_match is not None:
                    best = (
                        0,
                        source_type,
                        _direct_excerpt(text, direct_match),
                    )
                    break

        if best is not None:
            _, source_type, evidence_excerpt = best
            signals.append(
                _RoleSignal(
                    supports=support,
                    evidence=Evidence(
                        source_url=result.url,
                        source_type=source_type,
                        document_name=result.title or UNKNOWN,
                        page=NOT_APPLICABLE,
                        evidence_excerpt=evidence_excerpt,
                        retrieved_at=_retrieved_at(result.retrieved_at),
                    ),
                    primary_source=primary_source,
                )
            )

    return tuple(signals)


def _verification(signals: Iterable[_RoleSignal]) -> CompanyVerification:
    items = tuple(signals)
    manufacturing = any(
        item.supports == "explicit_manufacturing_evidence" for item in items
    )
    return CompanyVerification(
        explicit_manufacturing_evidence=manufacturing,
        primary_manufacturing_evidence=manufacturing
        and any(
            item.primary_source
            and item.supports == "explicit_manufacturing_evidence"
            for item in items
        ),
        explicit_distribution_evidence=any(
            item.supports == "explicit_distribution_evidence" for item in items
        ),
        explicit_trader_evidence=any(
            item.supports == "explicit_trader_evidence" for item in items
        ),
        official_domain_verified=None,
        manufacturer_independent_threshold_met=None,
        distributor_threshold_met=None,
    )


def _role(classification: CompanyClassification) -> str:
    if classification in {
        CompanyClassification.VERIFIED_MANUFACTURER,
        CompanyClassification.PROBABLE_MANUFACTURER,
    }:
        return "MANUFACTURER"
    if classification in {
        CompanyClassification.VERIFIED_DISTRIBUTOR,
        CompanyClassification.PROBABLE_DISTRIBUTOR,
    }:
        return "DISTRIBUTOR"
    return classification.value


def _expected_role(role: str | None) -> str | None:
    if role is None:
        return None
    if role.endswith("MANUFACTURER"):
        return "MANUFACTURER"
    if role.endswith("DISTRIBUTOR"):
        return "DISTRIBUTOR"
    if role in {"TRADER", "UNKNOWN"}:
        return role
    return None


def _serialize_signal(signal: _RoleSignal) -> dict[str, object]:
    evidence = signal.evidence
    retrieved_at = evidence.retrieved_at.isoformat().replace("+00:00", "Z")
    return {
        "supports": signal.supports,
        "source_url": evidence.source_url,
        "source_type": evidence.source_type,
        "document_name": evidence.document_name,
        "page": evidence.page,
        "evidence_excerpt": evidence.evidence_excerpt,
        "retrieved_at": retrieved_at,
    }


def _deduplicate_signals(signals: Iterable[_RoleSignal]) -> tuple[_RoleSignal, ...]:
    unique: dict[tuple[str, str, str], _RoleSignal] = {}
    for signal in signals:
        key = (
            signal.supports,
            signal.evidence.source_url,
            signal.evidence.evidence_excerpt,
        )
        unique.setdefault(key, signal)
    return tuple(unique.values())


def _result_id(result: SearchResult) -> str:
    value = f"{result.query}\0{result.url}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _classification_payload(
    *,
    target_entity: str,
    control_id: str | None,
    matched_by: tuple[str, ...],
    signals: tuple[_RoleSignal, ...],
) -> dict[str, object]:
    classified = classify_company(_verification(signals))
    return {
        "control_id": control_id,
        "target_entity": target_entity,
        "matched_by": list(matched_by),
        "role": _role(classified.classification),
        "detailed_classification": classified.classification.value,
        "reason_codes": list(classified.reason_codes),
        "evidence": [_serialize_signal(signal) for signal in signals],
    }


def _marketplace_payload(
    *,
    target_entity: str,
    control_id: str | None,
    matched_by: tuple[str, ...],
) -> dict[str, object]:
    return {
        "control_id": control_id,
        "target_entity": target_entity,
        "matched_by": list(matched_by),
        "role": "MARKETPLACE",
        "detailed_classification": "MARKETPLACE",
        "reason_codes": ["MARKETPLACE_DOMAIN_HUMAN_CONFIG"],
        "evidence": [],
    }


def _domain_alias(result: SearchResult) -> str:
    hostname = (urlsplit(result.url).hostname or UNKNOWN).casefold()
    hostname = hostname.removeprefix("www.")
    label = hostname.split(".", 1)[0]
    label_key = re.sub(r"[^a-z0-9]+", "", label)
    title_words = re.findall(r"[^\W_]+", result.title, flags=re.UNICODE)
    candidates: list[tuple[int, int, str]] = []
    for size in range(1, min(4, len(title_words)) + 1):
        for start in range(0, len(title_words) - size + 1):
            words = title_words[start : start + size]
            joined = re.sub(r"[^a-z0-9]+", "", "".join(words).casefold())
            if len(joined) < 4:
                continue
            if joined in label_key or label_key in joined:
                candidates.append(
                    (
                        0 if joined == label_key else 1,
                        abs(len(joined) - len(label_key)),
                        " ".join(words),
                    )
                )
    if candidates:
        return min(candidates, key=lambda item: (item[0], item[1]))[2]
    return label.replace("-", " ") or UNKNOWN


def _percentage(count: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(count / denominator * 100, 2)


def _role_distribution(result_rows: list[dict[str, object]]) -> dict[str, object]:
    classifications = [row["domain_classification"] for row in result_rows]
    marketplace_count = sum(
        classification["role"] == "MARKETPLACE"
        for classification in classifications
    )
    denominator = len(classifications) - marketplace_count
    roles: dict[str, object] = {}
    levels = {
        "MANUFACTURER": (
            "VERIFIED_MANUFACTURER",
            "PROBABLE_MANUFACTURER",
        ),
        "DISTRIBUTOR": (
            "VERIFIED_DISTRIBUTOR",
            "PROBABLE_DISTRIBUTOR",
        ),
    }
    for role in ("MANUFACTURER", "DISTRIBUTOR", "TRADER", "UNKNOWN"):
        count = sum(classification["role"] == role for classification in classifications)
        role_payload: dict[str, object] = {
            "count": count,
            "percentage": _percentage(count, denominator),
        }
        if role in levels:
            role_payload["levels"] = {
                level: {
                    "count": sum(
                        classification["detailed_classification"] == level
                        for classification in classifications
                    ),
                    "percentage": _percentage(
                        sum(
                            classification["detailed_classification"] == level
                            for classification in classifications
                        ),
                        denominator,
                    ),
                }
                for level in levels[role]
            }
        roles[role] = role_payload

    examples: dict[str, list[dict[str, object]]] = {}
    for role in ("MANUFACTURER", "DISTRIBUTOR", "TRADER"):
        role_examples: list[dict[str, object]] = []
        seen_domains: set[str] = set()
        for row, classification in zip(result_rows, classifications):
            if classification["role"] != role:
                continue
            domain = (urlsplit(row["url"]).hostname or "UNKNOWN_DOMAIN").casefold()
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            role_examples.append(
                {
                    "domain": domain,
                    "detailed_classification": classification[
                        "detailed_classification"
                    ],
                    "reason_codes": classification["reason_codes"],
                }
            )
            if len(role_examples) == 5:
                break
        examples[role] = role_examples

    unknown_signals: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    role_words = ("manufacturer", "producer", "fabricante", "distribuidor")
    for row, classification in zip(result_rows, classifications):
        if classification["role"] != "UNKNOWN":
            continue
        title = row["title"]
        if not any(word in title.casefold() for word in role_words):
            continue
        url = row["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unknown_signals.append(
            {
                "domain": (urlsplit(url).hostname or "UNKNOWN_DOMAIN").casefold(),
                "title": title,
                "reason_codes": classification["reason_codes"],
            }
        )
        if len(unknown_signals) == 10:
            break

    return {
        "total_results": len(classifications),
        "marketplace_results": marketplace_count,
        "role_denominator": denominator,
        "roles": roles,
        "examples_by_non_unknown_role": examples,
        "unknown_with_role_signal_in_title": unknown_signals,
    }


def _result_error_summary(result_rows: list[dict[str, object]]) -> dict[str, int | str]:
    hits = sum(row["result_comparison"] == "HIT" for row in result_rows)
    errors = sum(row["result_comparison"] == "ERROR" for row in result_rows)
    not_adjudicated = sum(
        row["result_comparison"] == "NOT_ADJUDICATED" for row in result_rows
    )
    marketplace_controls = sum(
        row["expected_domain_role"] == "MARKETPLACE" for row in result_rows
    )
    false_positive_errors = sum(
        row["domain_classification"]["role"] == "MANUFACTURER"
        and row["expected_domain_role"]
        in {"DISTRIBUTOR", "TRADER", "MARKETPLACE"}
        for row in result_rows
    )
    non_unknown_not_adjudicated = sum(
        row["result_comparison"] == "NOT_ADJUDICATED"
        and row["domain_classification"]["role"] != "UNKNOWN"
        for row in result_rows
    )
    return {
        "scope": "ALL_RESULTS",
        "total_results": len(result_rows),
        "evaluated_results": hits + errors,
        "hits": hits,
        "errors": errors,
        "false_positive_errors": false_positive_errors,
        "marketplace_controls": marketplace_controls,
        "not_adjudicated": not_adjudicated,
        "non_unknown_not_adjudicated": non_unknown_not_adjudicated,
    }


def _forbidden_violation(
    entity: BenchmarkEntity,
    *,
    role: str,
    detailed_classification: str,
) -> bool:
    detailed_roles = {item.value for item in CompanyClassification}
    for forbidden in entity.must_not_be:
        if forbidden in detailed_roles:
            if forbidden == detailed_classification:
                return True
            continue
        if forbidden in {"MANUFACTURER", "DISTRIBUTOR", "TRADER", "UNKNOWN"}:
            if forbidden == role:
                return True
    return False


def build_company_classification_report(
    category: str,
    results: Iterable[SearchResult],
    *,
    extracted_content_by_url: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Classify cassette search evidence, then compare it with human labels."""

    result_items = list(results)
    entities = load_benchmark_entities(category) or ()
    extracted_content = dict(extracted_content_by_url or {})
    marketplaces = MarketplaceDomainRegistry()
    signals_by_control: dict[str, list[_RoleSignal]] = {
        entity.control_id: [] for entity in entities
    }
    matched_results_by_control: dict[str, set[str]] = {
        entity.control_id: set() for entity in entities
    }
    result_rows: list[dict[str, object]] = []

    for result in result_items:
        is_marketplace = marketplaces.matches_url(result.url)
        extracted = extracted_content.get(result.url, "")
        if is_marketplace:
            domain_classification = _marketplace_payload(
                target_entity=(urlsplit(result.url).hostname or UNKNOWN),
                control_id=None,
                matched_by=("domain",),
            )
        else:
            domain_entity = BenchmarkEntity(
                control_id="",
                name=_domain_alias(result),
                expected_role=None,
                domains=((urlsplit(result.url).hostname or ""),),
                negative=False,
                must_not_be=(),
            )
            domain_classification = _classification_payload(
                target_entity=domain_entity.name,
                control_id=None,
                matched_by=("domain",),
                signals=_role_signals(
                    domain_entity,
                    result,
                    ("domain",),
                    extracted,
                ),
            )

        entity_rows: list[dict[str, object]] = []
        expected_domain_roles: set[str] = set()
        for entity in entities:
            matched_by = match_benchmark_entity(entity, result)
            if not matched_by:
                continue
            expected = _expected_role(entity.expected_role)
            if "domain" in matched_by and not entity.negative and expected is not None:
                expected_domain_roles.add(expected)
            signals = (
                ()
                if is_marketplace
                else _role_signals(entity, result, matched_by, extracted)
            )
            if not is_marketplace:
                signals_by_control[entity.control_id].extend(signals)
            matched_results_by_control[entity.control_id].add(_result_id(result))
            entity_rows.append(
                (
                    _marketplace_payload(
                        target_entity=entity.name,
                        control_id=entity.control_id,
                        matched_by=matched_by,
                    )
                    if is_marketplace
                    else _classification_payload(
                        target_entity=entity.name,
                        control_id=entity.control_id,
                        matched_by=matched_by,
                        signals=signals,
                    )
                )
            )

        if not entity_rows:
            entity_rows.append(
                _classification_payload(
                    target_entity=UNKNOWN,
                    control_id=None,
                    matched_by=(),
                    signals=(),
                )
            )
        if is_marketplace:
            expected_domain_role = "MARKETPLACE"
        elif len(expected_domain_roles) == 1:
            expected_domain_role = next(iter(expected_domain_roles))
        else:
            expected_domain_role = None
        if expected_domain_role is None:
            result_comparison = "NOT_ADJUDICATED"
        elif domain_classification["role"] == expected_domain_role:
            result_comparison = "HIT"
        else:
            result_comparison = "ERROR"
        result_rows.append(
            {
                "result_id": _result_id(result),
                "url": result.url,
                "title": result.title,
                "query": result.query,
                "sources_consulted": [result.url],
                "extracted_content_available": bool(extracted),
                "domain_classification": domain_classification,
                "entity_classifications": entity_rows,
                "expected_domain_role": expected_domain_role,
                "result_comparison": result_comparison,
            }
        )

    hits = 0
    errors = 0
    not_found = 0
    entity_rows = []
    negative_appeared = False
    negative_violations = 0

    for entity in entities:
        signals = _deduplicate_signals(signals_by_control[entity.control_id])
        matched_count = len(matched_results_by_control[entity.control_id])
        classified = classify_company(_verification(signals))
        role = _role(classified.classification)
        expected_role = _expected_role(entity.expected_role)

        if entity.negative:
            comparison = "NEGATIVE_CONTROL"
            if matched_count:
                negative_appeared = True
                violated = _forbidden_violation(
                    entity,
                    role=role,
                    detailed_classification=classified.classification.value,
                )
                negative_behavior = "VIOLATION" if violated else "SAFE"
                if violated:
                    negative_violations += 1
            else:
                negative_behavior = "NOT_APPEARED"
        elif not matched_count:
            comparison = "NOT_FOUND"
            negative_behavior = None
            if expected_role is not None:
                not_found += 1
        elif expected_role is None:
            comparison = "NOT_EVALUATED"
            negative_behavior = None
        elif role == expected_role:
            comparison = "HIT"
            negative_behavior = None
            hits += 1
        else:
            comparison = "ERROR"
            negative_behavior = None
            errors += 1

        entity_rows.append(
            {
                "control_id": entity.control_id,
                "entity": entity.name,
                "ground_truth_role": entity.expected_role,
                "expected_role": expected_role,
                "classification": role,
                "detailed_classification": classified.classification.value,
                "comparison": comparison,
                "matched_result_count": matched_count,
                "reason_codes": list(classified.reason_codes),
                "evidence": [_serialize_signal(signal) for signal in signals],
                "negative": entity.negative,
                "must_not_be": list(entity.must_not_be),
                "negative_behavior": negative_behavior,
            }
        )

    negative_behavior = (
        "NOT_APPEARED"
        if not negative_appeared
        else "FAIL"
        if negative_violations
        else "PASS"
    )
    return {
        "result_count": len(result_rows),
        "results": result_rows,
        "role_distribution": _role_distribution(result_rows),
        "result_error_summary": _result_error_summary(result_rows),
        "ground_truth_comparison": {
            "summary": {
                "hits": hits,
                "errors": errors,
                "not_found": not_found,
                "evaluated": hits + errors,
            },
            "entities": entity_rows,
            "negative": {
                "appeared": negative_appeared,
                "violations": negative_violations,
                "behavior": negative_behavior,
            },
        },
    }
