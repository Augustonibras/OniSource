from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

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
) -> tuple[_RoleSignal, ...]:
    target_pattern = _target_pattern(entity.name)
    fragments = (
        ("SEARCH_RESULT_TITLE", result.title),
        ("SEARCH_RESULT_SNIPPET", result.snippet),
        ("SEARCH_RESULT_CONTENT", result.content),
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
) -> dict[str, object]:
    """Classify cassette search evidence, then compare it with human labels."""

    result_items = list(results)
    entities = load_benchmark_entities(category) or ()
    signals_by_control: dict[str, list[_RoleSignal]] = {
        entity.control_id: [] for entity in entities
    }
    matched_results_by_control: dict[str, set[str]] = {
        entity.control_id: set() for entity in entities
    }
    result_rows: list[dict[str, object]] = []

    for result in result_items:
        entity_rows: list[dict[str, object]] = []
        for entity in entities:
            matched_by = match_benchmark_entity(entity, result)
            if not matched_by:
                continue
            signals = _role_signals(entity, result, matched_by)
            signals_by_control[entity.control_id].extend(signals)
            matched_results_by_control[entity.control_id].add(_result_id(result))
            entity_rows.append(
                _classification_payload(
                    target_entity=entity.name,
                    control_id=entity.control_id,
                    matched_by=matched_by,
                    signals=signals,
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
        result_rows.append(
            {
                "result_id": _result_id(result),
                "url": result.url,
                "title": result.title,
                "query": result.query,
                "sources_consulted": [result.url],
                "entity_classifications": entity_rows,
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
