from __future__ import annotations

from src.search.coverage import build_ground_truth_coverage
from src.search.models import SearchResult


def _result(url: str, title: str) -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        snippet="",
        content="",
        raw_score=1.0,
        provider="cassette",
        query="benchmark coverage",
        retrieved_at="2026-08-20T12:00:00Z",
    )


def _rows_by_id(coverage: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = coverage["entities"]
    assert isinstance(rows, list)
    return {row["control_id"]: row for row in rows}


def test_case_a_coverage_matches_names_without_classifying_roles() -> None:
    coverage = build_ground_truth_coverage(
        "titanium_dioxide",
        [
            _result("https://www.lomonbillions.global/r996", "BILLIONS R-996 - LB Group"),
            _result("https://www.tronox.com/", "Tronox titanium dioxide"),
            _result("https://www.kronosww.com/", "KRONOS titanium dioxide"),
        ],
    )

    assert coverage is not None
    rows = _rows_by_id(coverage)
    assert len(rows) == 6
    assert rows["lb_group"]["status"] == "ENCONTRADO"
    assert rows["tronox"]["status"] == "ENCONTRADO"
    assert rows["kronos"]["status"] == "ENCONTRADO"
    assert rows["omya_do_brasil"]["status"] == "NÃO ENCONTRADO"
    assert rows["qingdao_lidayouxuan"]["negative"] is True
    assert coverage["negative_appeared"] is False
    assert coverage["total"] == "fabricantes 3/3, distribuidores 0/2"


def test_case_b_coverage_matches_domains_and_signals_negative_presence() -> None:
    coverage = build_ground_truth_coverage(
        "phosphoric_acid",
        [
            _result("https://www.icl-group.com/product", "Phosphoric Acid"),
            _result("https://gjchemical.com/phosphoric-acid", "Product page"),
            _result(
                "https://www.mahaco.biz/phosphoric-acid",
                "Zhengzhou MAHACO Industrial Co., Ltd",
            ),
            _result("https://us.metoree.com/categories/phosphoric-acid", "Directory"),
        ],
    )

    assert coverage is not None
    rows = _rows_by_id(coverage)
    assert len(rows) == 8
    assert rows["icl_group"]["status"] == "ENCONTRADO"
    assert rows["gj_chemical"]["matched_by"] == ["domain"]
    assert rows["zhengzhou_mahaco_industrial"]["matched_by"] == ["domain", "name"]
    assert rows["cobase_group"]["status"] == "NÃO ENCONTRADO"
    assert rows["metoree_directory"]["status"] == "ENCONTRADO"
    assert rows["metoree_directory"]["negative"] is True
    assert coverage["negative_appeared"] is True
    assert coverage["total"] == "fabricantes 1/4, distribuidores 1/1"


def test_category_without_human_benchmark_has_no_coverage_block() -> None:
    assert build_ground_truth_coverage("unconfigured_category", []) is None
