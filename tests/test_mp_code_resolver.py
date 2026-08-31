from __future__ import annotations

import pytest

from src.mp_code_resolver import (
    MPCodeNotFoundError,
    MPCodeResolver,
    build_external_search_query,
)


def test_supported_mp_code_forms_resolve_to_the_same_product() -> None:
    resolver = MPCodeResolver()

    resolutions = [resolver.resolve(value) for value in ("MP 041", "MP041", "041")]

    assert {item.product_name for item in resolutions} == {
        "ácido fosfórico industrial"
    }
    assert [item.input_mp_code for item in resolutions] == ["MP 041", "MP041", "041"]
    assert {item.catalog_mp_code for item in resolutions} == {"MP 041"}
    assert {item.cas_number for item in resolutions} == {"7664-38-2"}


def test_missing_mp_code_raises_explicit_error_without_fallback() -> None:
    resolver = MPCodeResolver()

    with pytest.raises(MPCodeNotFoundError) as captured:
        resolver.resolve("MP 999")

    assert captured.value.input_mp_code == "MP 999"
    assert "does not exist in the internal catalog" in str(captured.value)
    assert "no fallback was used" in str(captured.value)


@pytest.mark.parametrize("input_mp_code", ["MP 041", "MP041", "041"])
def test_internal_mp_code_never_appears_in_generated_query(
    input_mp_code: str,
) -> None:
    resolution = MPCodeResolver().resolve(input_mp_code)

    query = build_external_search_query(resolution)

    assert query == resolution.product_name
    assert "MP 041" not in query
    assert "MP041" not in query
    assert "041" not in query
