from __future__ import annotations

from pathlib import Path

import pytest

from src.models import CompanyClassification
from src.search.company_classifier import (
    PROMPT_VERSION,
    ClassificationResult,
    CompanyClassifier,
    Confidence,
    LLMCompanyClassifier,
    LLMProvider,
    RuleBasedCompanyClassifier,
    build_llm_company_classifier_prompt,
    classify_with_citation_gate,
    llm_cache_key,
    read_llm_cache,
    write_llm_cache,
)


class _RejectingProvider(LLMProvider):
    def complete(self, prompt: str) -> str:
        raise AssertionError("the LLM provider must not be called")


class _UncitedClassifier(CompanyClassifier):
    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
    ) -> ClassificationResult:
        return ClassificationResult(
            role=CompanyClassification.VERIFIED_MANUFACTURER,
            confidence=Confidence.HIGH,
            citation="",
            reasoning="Unsupported classifier output.",
        )


def _cached_response(citation: str) -> dict[str, object]:
    return {
        "role": "PROBABLE_MANUFACTURER",
        "confidence": "MEDIUM",
        "citation": citation,
        "reasoning": "The page explicitly describes own production.",
    }


def test_consumer_forces_unknown_when_citation_is_empty() -> None:
    result = classify_with_citation_gate(
        _UncitedClassifier(),
        "example.com",
        "Example",
        "Example content",
    )

    assert result.role is CompanyClassification.UNKNOWN
    assert result.citation == ""


def test_rule_based_adapter_preserves_rule_output_but_has_no_citation() -> None:
    classifier = RuleBasedCompanyClassifier()
    content = (
        "We manufacture titanium dioxide. "
        "Our production capacity is 100,000 tons per year."
    )

    raw_result = classifier.classify("example.com", "Example", content)
    consumed_result = classify_with_citation_gate(
        classifier,
        "example.com",
        "Example",
        content,
    )

    assert raw_result.role is CompanyClassification.PROBABLE_MANUFACTURER
    assert raw_result.citation == ""
    assert consumed_result.role is CompanyClassification.UNKNOWN


def test_llm_cache_helpers_round_trip_json(tmp_path: Path) -> None:
    key = llm_cache_key("example.com", "Example", "Own production", PROMPT_VERSION)
    response = _cached_response("Own production")

    path = write_llm_cache(tmp_path, key, response)

    assert path == tmp_path / f"{key}.json"
    assert read_llm_cache(tmp_path, key) == response


def test_llm_classifier_cache_hit_is_parsed_without_provider_call(
    tmp_path: Path,
) -> None:
    domain = "example.com"
    title = "Example producer"
    content = "We operate our own production plant in Example City."
    citation = "our own production plant"
    key = llm_cache_key(domain, title, content, PROMPT_VERSION)
    write_llm_cache(tmp_path, key, _cached_response(citation))
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content)

    assert result == ClassificationResult(
        role=CompanyClassification.PROBABLE_MANUFACTURER,
        confidence=Confidence.MEDIUM,
        citation=citation,
        reasoning="The page explicitly describes own production.",
    )


def test_llm_classifier_cache_miss_is_explicit_and_offline(tmp_path: Path) -> None:
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    with pytest.raises(NotImplementedError, match="LLM provider not configured"):
        classifier.classify("missing.example", "Missing", "No cached response")

    assert list(tmp_path.iterdir()) == []


def test_cached_citation_must_be_literal_extracted_content(tmp_path: Path) -> None:
    domain = "example.com"
    title = "Example"
    content = "The page contains no production statement."
    key = llm_cache_key(domain, title, content, PROMPT_VERSION)
    write_llm_cache(tmp_path, key, _cached_response("Invented production claim"))
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    with pytest.raises(ValueError, match="not literal extracted content"):
        classifier.classify(domain, title, content)


def test_prompt_requires_strict_json_and_literal_citation() -> None:
    prompt = build_llm_company_classifier_prompt(
        "example.com",
        "Example",
        "Extracted evidence",
    )

    assert '"role":"UNKNOWN"' in prompt
    assert '"confidence":"LOW"' in prompt
    assert '"citation":""' in prompt
    assert '"reasoning":"short evidence-based reason"' in prompt
    assert "literal, contiguous excerpt copied exactly from extracted_content" in prompt
    assert PROMPT_VERSION == "v1"
