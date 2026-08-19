from __future__ import annotations

import pytest

from src.mp_code_resolver import MPCodeResolver
from src.search.query_builder import (
    InternalMPCodeError,
    QueryLimitExceededError,
    build_search_queries,
)


def test_query_builder_uses_versioned_role_templates() -> None:
    queries = build_search_queries("phosphoric acid", category="industrial chemical")

    assert len(queries) == 10
    assert "phosphoric acid manufacturer" in queries
    assert "phosphoric acid industrial chemical technical data sheet" in queries


def test_query_builder_rejects_more_than_twelve_queries(tmp_path) -> None:
    template_path = tmp_path / "too_many.yaml"
    template_path.write_text(
        "base_templates:\n"
        + "".join(
            f'  - "{{product_name}} manufacturer"\n' for _ in range(13)
        )
        + "category_templates:\n",
        encoding="utf-8",
    )

    with pytest.raises(QueryLimitExceededError, match="maximum is 12"):
        build_search_queries("phosphoric acid", template_path=template_path)


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
