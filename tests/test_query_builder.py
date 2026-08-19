from __future__ import annotations

import pytest

from src.mp_code_resolver import MPCodeResolver
from src.search.query_builder import (
    InternalMPCodeError,
    QueryLimitExceededError,
    build_search_queries,
)


def test_query_builder_uses_versioned_role_templates() -> None:
    queries = build_search_queries(
        "phosphoric acid",
        category="industrial chemical",
        category_config={"cas_number": "7664-38-2", "branded": True},
    )

    assert len(queries) == 11
    assert "phosphoric acid manufacturer" in queries
    assert "industrial chemical producers list" in queries
    assert "7664-38-2 manufacturer" in queries
    assert "phosphoric acid distribuidor Brasil" in queries


@pytest.mark.parametrize(
    ("product_name", "category", "category_config", "expected_queries"),
    [
        (
            "BILLIONS R996 Titanium Dioxide",
            "Titanium Dioxide",
            {
                "cas_numbers": ["13463-67-7", "1317-80-2"],
                "branded": True,
            },
            {
                "Titanium Dioxide manufacturer",
                "Titanium Dioxide producers list",
            },
        ),
        (
            "Phosphoric Acid",
            "Phosphoric Acid",
            {"cas_number": "7664-38-2", "branded": False},
            {
                "Phosphoric Acid manufacturer",
                "Phosphoric Acid producers list",
            },
        ),
    ],
)
def test_phase_zero_cases_render_category_templates(
    product_name: str,
    category: str,
    category_config: dict[str, object],
    expected_queries: set[str],
) -> None:
    queries = build_search_queries(
        product_name,
        category=category,
        category_config=category_config,
    )

    assert expected_queries.issubset(queries)


def test_query_builder_rejects_more_than_twelve_queries(tmp_path) -> None:
    template_path = tmp_path / "too_many.yaml"
    template_path.write_text(
        "base_templates:\n"
        + "".join(
            '  - "{product_name} manufacturer'
            + ' {product_name}' * repetition
            + '"\n'
            for repetition in range(13)
        )
        + "category_templates:\n"
        + "cas_templates:\n"
        + "market_templates:\n",
        encoding="utf-8",
    )

    with pytest.raises(QueryLimitExceededError, match="maximum is 12"):
        build_search_queries("phosphoric acid", template_path=template_path)


def test_category_templates_render_when_category_is_in_product_name() -> None:
    queries = build_search_queries(
        "BILLIONS R996 Titanium Dioxide",
        category="tItAnIuM dIoXiDe",
    )

    assert "tItAnIuM dIoXiDe manufacturer" in queries
    assert "tItAnIuM dIoXiDe producers list" in queries
    assert "tItAnIuM dIoXiDe distribuidor Brasil" in queries


def test_cas_templates_are_skipped_when_category_config_has_no_cas_number() -> None:
    queries = build_search_queries(
        "BILLIONS R996 Titanium Dioxide",
        category="Titanium Dioxide",
        category_config={"category": "titanium_dioxide", "branded": True},
    )

    assert len(queries) == 10
    assert all("cas_number" not in query for query in queries)


def test_cas_number_is_rendered_only_from_category_config() -> None:
    queries = build_search_queries(
        "Phosphoric Acid",
        category="Phosphoric Acid",
        category_config={"cas_number": "7664-38-2"},
    )

    assert "7664-38-2 manufacturer" in queries


def test_each_configured_cas_number_renders_one_query() -> None:
    queries = build_search_queries(
        "BILLIONS R996 Titanium Dioxide",
        category="Titanium Dioxide",
        category_config={
            "cas_numbers": ["13463-67-7", "1317-80-2"],
            "branded": True,
        },
    )

    assert "13463-67-7 manufacturer" in queries
    assert "1317-80-2 manufacturer" in queries
    assert len(queries) == 12


def test_duplicate_configured_cas_numbers_produce_one_unique_query() -> None:
    queries = build_search_queries(
        "Phosphoric Acid",
        category="Phosphoric Acid",
        category_config={
            "cas_numbers": ["7664-38-2", "  7664-38-2  "],
        },
    )

    assert queries.count("7664-38-2 manufacturer") == 1


def test_multiple_cas_queries_still_obey_unique_query_limit() -> None:
    with pytest.raises(QueryLimitExceededError, match="14 unique queries"):
        build_search_queries(
            "Example Product",
            category="Example Product",
            category_config={
                "cas_numbers": [f"10000-00-{index}" for index in range(6)],
                "branded": True,
            },
        )


def test_rendered_queries_are_deduplicated_by_spaces_and_case() -> None:
    queries = build_search_queries(
        "Phosphoric Acid",
        category="  PHOSPHORIC   ACID  ",
    )

    market_query = "phosphoric acid distribuidor brasil"
    assert sum(query.casefold() == market_query for query in queries) == 1
    assert len(queries) == 6


def test_equivalence_templates_are_absent_when_human_marks_not_branded() -> None:
    queries = build_search_queries(
        "Phosphoric Acid",
        category="Phosphoric Acid",
        category_config={
            "branded": False,
            "cas_number": "7664-38-2",
        },
    )

    assert "Phosphoric Acid equivalent" not in queries
    assert "Phosphoric Acid alternative" not in queries


@pytest.mark.parametrize("input_mp_code", ["MP 041", "MP041", "041"])
def test_resolved_internal_mp_code_never_appears_in_generated_queries(
    input_mp_code: str,
) -> None:
    resolved = MPCodeResolver().resolve(input_mp_code)

    queries = build_search_queries(resolved.product_name)

    assert all("MP 041" not in query for query in queries)
    assert all("MP041" not in query for query in queries)
    assert all("041" not in query for query in queries)
    assert all(resolved.product_name in query for query in queries)


@pytest.mark.parametrize("raw_code", ["MP 041", "MP041", "041"])
def test_query_builder_rejects_internal_code_as_product_name(raw_code: str) -> None:
    with pytest.raises(InternalMPCodeError):
        build_search_queries(raw_code)
