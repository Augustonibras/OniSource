from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.models import CompanyClassification
from src.search.company_classifier import (
    CONTENT_BUDGET_POLICY,
    LLM_FAILURE_REASONS,
    MAX_CONTENT_CHARS,
    PAGE_BREAK,
    PROMPT_VERSION,
    TRUNCATED_MARKER,
    ClassificationResult,
    CompanyClassifier,
    Confidence,
    LLMCompanyClassifier,
    LLMProvider,
    RuleBasedCompanyClassifier,
    SupplierRole,
    budget_extracted_content,
    build_llm_company_classifier_prompt,
    classify_with_citation_gate,
    group_extracted_pages_by_domain,
    llm_cache_key,
    normalize_classifier_domain,
    read_llm_cache,
    rule_role_to_supplier_role,
    write_llm_cache,
)
from src.search.models import SearchResult


PRODUCT_CONTEXT = "titanium dioxide, rutile grade, CAS 13463-67-7"


class _RejectingProvider(LLMProvider):
    def complete(self, prompt: str) -> str:
        raise AssertionError("the LLM provider must not be called")


class _UncitedLLMClassifier(CompanyClassifier):
    requires_citation = True

    def classify(
        self,
        domain: str,
        title: str,
        extracted_content: str,
        product_context: str,
        **kwargs,
    ) -> ClassificationResult:
        return ClassificationResult(
            role=SupplierRole.MANUFACTURER,
            confidence=Confidence.HIGH,
            citation="",
            reasoning="Unsupported classifier output.",
        )


def _cached_response(
    citation: str,
    *,
    confidence: str = "MEDIUM",
    needs_review: bool = False,
) -> dict[str, object]:
    return {
        "role": "MANUFACTURER",
        "confidence": confidence,
        "citation": citation,
        "reasoning": "The page explicitly describes own production.",
        "needs_review": needs_review,
    }


def _key(domain: str, title: str, content: str) -> str:
    return llm_cache_key(
        domain,
        title,
        content,
        PRODUCT_CONTEXT,
        PROMPT_VERSION,
    )


def test_supplier_role_matches_the_human_ground_truth_vocabulary() -> None:
    assert [role.value for role in SupplierRole] == [
        "MANUFACTURER",
        "DISTRIBUTOR",
        "TRADER",
        "MARKETPLACE_OR_DIRECTORY",
        "NOT_A_SUPPLIER",
        "NOT_A_COMPANY",
        "UNCERTAIN",
        "UNKNOWN",
    ]


def _search_result(url: str, title: str) -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        snippet="",
        content="",
        raw_score=1.0,
        provider="cassette",
        query="test",
        retrieved_at="2026-08-24T00:00:00Z",
    )


def test_domain_normalization_preserves_www_and_other_subdomains() -> None:
    assert normalize_classifier_domain("HTTPS://WWW.Example.COM:443/") == (
        "www.example.com"
    )
    assert normalize_classifier_domain("example.com:8443/") == "example.com"
    assert normalize_classifier_domain("en.cjnphos.com") == "en.cjnphos.com"
    assert normalize_classifier_domain("www.cjnphos.com") == "www.cjnphos.com"
    assert normalize_classifier_domain("www.example.com") != (
        normalize_classifier_domain("example.com")
    )


def test_extracted_pages_are_grouped_once_per_domain_in_result_order() -> None:
    first_url = "https://en.example.com/first"
    second_url = "https://en.example.com/second"
    www_url = "https://www.example.com/page"
    results = [
        _search_result(first_url, "First title"),
        _search_result(second_url, "Second title"),
        _search_result(first_url, "Duplicate search result"),
        _search_result(www_url, "WWW title"),
    ]

    grouped = group_extracted_pages_by_domain(
        results,
        {
            first_url: "First page content",
            second_url: "Second page content",
            www_url: "WWW page content",
        },
    )
    grouped_with_reversed_mapping = group_extracted_pages_by_domain(
        results,
        {
            www_url: "WWW page content",
            second_url: "Second page content",
            first_url: "First page content",
        },
    )

    assert [item.domain for item in grouped] == [
        "en.example.com",
        "www.example.com",
    ]
    assert grouped[0].title == "First title"
    assert grouped[0].page_count == 2
    assert grouped[0].source_urls == (first_url, second_url)
    assert grouped[0].extracted_content == (
        f"First page content{PAGE_BREAK}Second page content"
    )
    assert grouped[1].page_count == 1
    assert grouped_with_reversed_mapping == grouped


def test_domain_grouping_preserves_marketplace_and_noise_signals() -> None:
    marketplace_url = "https://www.alibaba.com/product"
    noise_url = "https://agency.gov/document"
    results = [
        replace(
            _search_result(marketplace_url, "Marketplace"),
            marketplace_signal=True,
            marketplace_signal_reason="MARKETPLACE_DOMAIN:alibaba.com",
        ),
        replace(
            _search_result(noise_url, "Agency"),
            noise_signal=True,
            noise_signal_reason="LOCAL_SUFFIX:.gov",
        ),
    ]

    grouped = group_extracted_pages_by_domain(
        results,
        {marketplace_url: "Marketplace page", noise_url: "Government page"},
    )

    assert grouped[0].marketplace_signal is True
    assert grouped[0].marketplace_signal_reasons == (
        "MARKETPLACE_DOMAIN:alibaba.com",
    )
    assert grouped[1].noise_signal is True
    assert grouped[1].noise_signal_reasons == ("LOCAL_SUFFIX:.gov",)


def test_per_page_budget_redistributes_unused_quota_in_successive_passes() -> None:
    first = "A" * 50_000
    second = "B" * 30_000
    short = "C" * 1_000

    budgeted = budget_extracted_content(
        PAGE_BREAK.join((first, second, short))
    )
    pages = budgeted.content.split(PAGE_BREAK)

    assert budgeted.page_allocations == (19_500, 19_500, 1_000)
    assert budgeted.evidence_truncated is True
    assert pages[0] == first[:19_500] + TRUNCATED_MARKER
    assert pages[1] == second[:19_500] + TRUNCATED_MARKER
    assert pages[2] == short


def test_short_page_returns_its_quota_without_unnecessary_truncation() -> None:
    first = "A" * 30_000
    short = "B" * 1_000

    budgeted = budget_extracted_content(PAGE_BREAK.join((first, short)))

    assert budgeted.page_allocations == (30_000, 1_000)
    assert budgeted.evidence_truncated is False
    assert budgeted.content == PAGE_BREAK.join((first, short))


def test_fixed_rule_roles_are_mapped_explicitly_without_fallback_inference() -> None:
    assert rule_role_to_supplier_role(
        CompanyClassification.PROBABLE_MANUFACTURER
    ) is SupplierRole.MANUFACTURER
    assert rule_role_to_supplier_role(
        CompanyClassification.VERIFIED_DISTRIBUTOR
    ) is SupplierRole.DISTRIBUTOR
    assert rule_role_to_supplier_role("MARKETPLACE") is (
        SupplierRole.MARKETPLACE_OR_DIRECTORY
    )
    assert rule_role_to_supplier_role("NOT_A_COMPANY") is SupplierRole.NOT_A_COMPANY
    assert rule_role_to_supplier_role("UNMAPPED_RULE_VALUE") is SupplierRole.UNKNOWN


def test_citation_gate_applies_only_to_classifiers_that_require_it() -> None:
    gated = classify_with_citation_gate(
        _UncitedLLMClassifier(),
        "example.com",
        "Example",
        "Example content",
        PRODUCT_CONTEXT,
    )

    assert gated.role is SupplierRole.UNKNOWN
    assert gated.reasoning == "NO_CITATION"


def test_rule_based_adapter_keeps_its_prediction_without_a_citation_gate() -> None:
    classifier = RuleBasedCompanyClassifier()
    content = (
        "We manufacture titanium dioxide. "
        "Our production capacity is 100,000 tons per year."
    )

    raw_result = classifier.classify(
        "example.com",
        "Example",
        content,
        PRODUCT_CONTEXT,
    )
    consumed_result = classify_with_citation_gate(
        classifier,
        "example.com",
        "Example",
        content,
        PRODUCT_CONTEXT,
    )

    assert classifier.requires_citation is False
    assert raw_result.role is SupplierRole.MANUFACTURER
    assert raw_result.citation == ""
    assert consumed_result.role is SupplierRole.MANUFACTURER


def test_llm_cache_helpers_round_trip_json(tmp_path: Path) -> None:
    key = _key("example.com", "Example", "Own production")
    response = _cached_response("Own production")

    path = write_llm_cache(tmp_path, key, response)

    assert path == tmp_path / f"{key}.json"
    assert read_llm_cache(tmp_path, key) == response


def test_cache_key_changes_with_product_context() -> None:
    first = llm_cache_key("example.com", "Example", "Content", "product A")
    second = llm_cache_key("example.com", "Example", "Content", "product B")

    assert first != second


def test_cache_key_changes_with_model() -> None:
    first = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
        model="model-a",
    )
    second = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
        model="model-b",
    )

    assert first != second


def test_cache_key_and_prompt_include_retrieval_signals() -> None:
    baseline = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
    )
    signaled = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
        marketplace_signal=True,
        marketplace_signal_reason="MARKETPLACE_DOMAIN:example.com",
    )
    prompt = build_llm_company_classifier_prompt(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
        marketplace_signal=True,
        marketplace_signal_reason="MARKETPLACE_DOMAIN:example.com",
    )

    assert signaled != baseline
    assert "marketplace_signal:\ntrue" in prompt
    assert "MARKETPLACE_DOMAIN:example.com" in prompt


def test_cache_key_and_prompt_use_only_truncated_content() -> None:
    common_prefix = "a" * MAX_CONTENT_CHARS
    first = llm_cache_key(
        "example.com",
        "Example",
        common_prefix + "FIRST_SUFFIX",
        PRODUCT_CONTEXT,
    )
    second = llm_cache_key(
        "example.com",
        "Example",
        common_prefix + "SECOND_SUFFIX",
        PRODUCT_CONTEXT,
    )
    changed_within_limit = llm_cache_key(
        "example.com",
        "Example",
        "b" + common_prefix[1:],
        PRODUCT_CONTEXT,
    )
    prompt = build_llm_company_classifier_prompt(
        "example.com",
        "Example",
        common_prefix + "FIRST_SUFFIX",
        PRODUCT_CONTEXT,
    )

    assert first == second
    assert first != changed_within_limit
    assert "FIRST_SUFFIX" not in prompt
    assert prompt.endswith(common_prefix + TRUNCATED_MARKER + "\n")


def test_cache_key_contains_limit_and_budget_policy(monkeypatch) -> None:
    import src.search.company_classifier as classifier_module

    baseline = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
    )
    monkeypatch.setattr(
        classifier_module,
        "CONTENT_BUDGET_POLICY",
        "different_policy",
    )
    policy_changed = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
    )
    monkeypatch.setattr(
        classifier_module,
        "CONTENT_BUDGET_POLICY",
        CONTENT_BUDGET_POLICY,
    )
    monkeypatch.setattr(classifier_module, "MAX_CONTENT_CHARS", 39_999)
    limit_changed = llm_cache_key(
        "example.com",
        "Example",
        "Content",
        PRODUCT_CONTEXT,
    )

    assert policy_changed != baseline
    assert limit_changed != baseline


def test_llm_classifier_cache_hit_is_parsed_without_provider_call(
    tmp_path: Path,
) -> None:
    domain = "example.com"
    title = "Example producer"
    content = "We operate our own production plant in Example City."
    citation = "our own production plant"
    write_llm_cache(tmp_path, _key(domain, title, content), _cached_response(citation))
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result == ClassificationResult(
        role=SupplierRole.MANUFACTURER,
        confidence=Confidence.MEDIUM,
        citation=citation,
        reasoning="The page explicitly describes own production.",
        needs_review=False,
        evidence_truncated=False,
    )
    assert classifier.execution_metrics["failure_counts"] == {
        reason: 0 for reason in LLM_FAILURE_REASONS
    }


def test_citation_comparison_normalizes_whitespace(tmp_path: Path) -> None:
    domain = "example.com"
    title = "Example producer"
    content = "We operate\nour   own production plant\tin Example City."
    citation = "our own production plant in Example City."
    write_llm_cache(tmp_path, _key(domain, title, content), _cached_response(citation))
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result.role is SupplierRole.MANUFACTURER
    assert result.citation == citation


def test_low_confidence_forces_needs_review_true(tmp_path: Path) -> None:
    domain = "example.com"
    title = "Example supplier"
    content = "We sell titanium dioxide to industrial customers."
    citation = "We sell titanium dioxide"
    write_llm_cache(
        tmp_path,
        _key(domain, title, content),
        _cached_response(citation, confidence="LOW", needs_review=False),
    )
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result.confidence is Confidence.LOW
    assert result.needs_review is True


def test_explicit_needs_review_is_preserved(tmp_path: Path) -> None:
    domain = "example.com"
    title = "Example supplier"
    content = "We operate three factories for titanium dioxide."
    citation = "We operate three factories"
    write_llm_cache(
        tmp_path,
        _key(domain, title, content),
        _cached_response(citation, needs_review=True),
    )
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result.needs_review is True


def test_empty_citation_becomes_unknown_and_is_counted(tmp_path: Path) -> None:
    domain = "example.com"
    title = "Example"
    content = "No role evidence."
    write_llm_cache(tmp_path, _key(domain, title, content), _cached_response(""))
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result.role is SupplierRole.UNKNOWN
    assert result.reasoning == "NO_CITATION"
    assert classifier.execution_metrics["failure_counts"]["NO_CITATION"] == 1


def test_missing_citation_text_becomes_unknown_and_is_counted(tmp_path: Path) -> None:
    domain = "example.com"
    title = "Example"
    content = "The page contains no production statement."
    write_llm_cache(
        tmp_path,
        _key(domain, title, content),
        _cached_response("Invented production claim"),
    )
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result.role is SupplierRole.UNKNOWN
    assert result.reasoning == "CITATION_NOT_FOUND"
    assert classifier.execution_metrics["failure_counts"]["CITATION_NOT_FOUND"] == 1


@pytest.mark.parametrize(
    ("response", "raw_malformed_json"),
    [
        ({"role": "MANUFACTURER"}, False),
        (
            {
                "role": "UNSUPPORTED_ROLE",
                "confidence": "HIGH",
                "citation": "Evidence",
                "reasoning": "Reason",
                "needs_review": False,
            },
            False,
        ),
        (
            {
                "role": "MANUFACTURER",
                "confidence": "HIGH",
                "citation": "Evidence",
                "reasoning": "Reason",
                "needs_review": "false",
            },
            False,
        ),
        (None, True),
    ],
    ids=("missing-field", "unknown-enum", "invalid-review", "invalid-json"),
)
def test_invalid_responses_become_unknown_and_are_counted(
    tmp_path: Path,
    response: object,
    raw_malformed_json: bool,
) -> None:
    domain = "example.com"
    title = "Example"
    content = "Evidence"
    key = _key(domain, title, content)
    if raw_malformed_json:
        (tmp_path / f"{key}.json").write_text("{invalid", encoding="utf-8")
    else:
        write_llm_cache(tmp_path, key, response)
    classifier = LLMCompanyClassifier(_RejectingProvider(), tmp_path)

    result = classifier.classify(domain, title, content, PRODUCT_CONTEXT)

    assert result.role is SupplierRole.UNKNOWN
    assert result.reasoning == "INVALID_RESPONSE"
    assert classifier.execution_metrics["failure_counts"]["INVALID_RESPONSE"] == 1


def test_llm_classifier_cache_miss_raise_stays_explicit_and_offline(
    tmp_path: Path,
) -> None:
    classifier = LLMCompanyClassifier(
        _RejectingProvider(),
        tmp_path,
        on_miss="raise",
    )

    with pytest.raises(NotImplementedError, match="LLM provider not configured"):
        classifier.classify(
            "missing.example",
            "Missing",
            "No cached response",
            PRODUCT_CONTEXT,
        )

    assert list(tmp_path.iterdir()) == []


def test_llm_classifier_dry_run_writes_pending_prompt_and_counts_unique_call(
    tmp_path: Path,
) -> None:
    classifier = LLMCompanyClassifier(
        _RejectingProvider(),
        tmp_path,
        on_miss="dry_run",
    )

    first = classifier.classify(
        "example.com",
        "Example",
        "Extracted evidence",
        PRODUCT_CONTEXT,
    )
    second = classifier.classify(
        "example.com",
        "Example",
        "Extracted evidence",
        PRODUCT_CONTEXT,
    )
    pending = list((tmp_path / "_pending").glob("*.prompt.txt"))
    prompt = pending[0].read_text(encoding="utf-8")

    assert first.role is SupplierRole.UNKNOWN
    assert first.reasoning == "CACHE_MISS_DRY_RUN"
    assert first.evidence_truncated is False
    assert second == first
    assert len(pending) == 1
    assert PRODUCT_CONTEXT in prompt
    assert classifier.execution_metrics == {
        "provider_calls_planned": 1,
        "total_prompt_characters": len(prompt),
        "estimated_input_tokens": len(prompt) / 4,
        "token_estimation_method": "characters / 4",
        "failure_counts": {reason: 0 for reason in LLM_FAILURE_REASONS},
    }


def test_prompt_uses_human_taxonomy_product_context_and_strict_json() -> None:
    prompt = build_llm_company_classifier_prompt(
        "example.com",
        "Example",
        "Extracted evidence",
        PRODUCT_CONTEXT,
    )

    for role in SupplierRole:
        assert f"- {role.value}:" in prompt
    assert PRODUCT_CONTEXT in prompt
    assert "always be relative to product_context" in prompt
    assert '"role":"UNKNOWN"' in prompt
    assert '"confidence":"LOW"' in prompt
    assert '"citation":""' in prompt
    assert '"reasoning":"short evidence-based reason"' in prompt
    assert '"needs_review":true' in prompt
    assert "whitespace may be normalized" in prompt
    assert "classify the entity that owns the domain" in prompt
    assert "discontinued, sold out, or out-of-line product" in prompt
    assert "published on the company's own site" in prompt
    assert "A trading company that publishes a ranking remains a trading company" in prompt
    assert "classify according to the commercial content" in prompt
    assert "Role precedence (apply before the numbered commercial-role rules)" in prompt
    assert "Once the DISTRIBUTOR rule matches" in prompt
    assert '"distributor", "dealer", "reseller", "authorized distributor"' in prompt
    assert "warehousing or fulfillment" in prompt
    assert "A distributor has a public identity tied to reselling identifiable brands" in prompt
    assert "Decision rules (apply in this exact order after the role-precedence checks)" in prompt
    assert "third-party brands is decisive for TRADER" in prompt
    assert "Multiple self-declared roles mean TRADER" in prompt
    assert "MANUFACTURER requires both an active first-person own-production verb" in prompt
    assert "production capacity stated numerically" in prompt
    assert '"WOTAIchem operates three dedicated titanium dioxide manufacturing plants in China"' in prompt
    assert '"ICL operates phosphoric acid plants in Israel and China with combined capacity of 1.2M tons"' in prompt
    assert '"Veeransh Chemicals manufactures and supplies Phosphoric Acid to Vietnam"' in prompt
    assert '"SNDB uses state-of-the-art manufacturing processes such as the wet process"' in prompt
    assert "A generic manufacturer label without an active production verb" in prompt
    assert "The intermediation fallback is subordinate" in prompt
    assert "specific own-facility evidence required by rule 3" in prompt
    assert "classify the entity as TRADER and set needs_review to true" in prompt
    assert "does not need to prove the exact role" in prompt
    assert "needs_review must be true" in prompt
    assert MAX_CONTENT_CHARS == 40_000
    assert CONTENT_BUDGET_POLICY == "per_page_equal_quota_redistribute_v1"
    assert PROMPT_VERSION == "v9"
