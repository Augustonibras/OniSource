from __future__ import annotations

from src.search.company_evaluation import build_company_classification_report
from src.search.models import SearchResult


def _result(
    url: str,
    title: str,
    content: str,
    *,
    query: str = "phase zero query",
) -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        snippet="",
        content=content,
        raw_score=1.0,
        provider="cassette",
        query=query,
        retrieved_at="2026-08-20T12:00:00Z",
    )


def _entity_rows(report: dict[str, object]) -> dict[str, dict[str, object]]:
    comparison = report["ground_truth_comparison"]
    assert isinstance(comparison, dict)
    rows = comparison["entities"]
    assert isinstance(rows, list)
    return {row["control_id"]: row for row in rows}


def test_every_search_result_receives_an_evidence_aware_role() -> None:
    results = [
        _result(
            "https://www.icl-group.com/phosphoric-acid",
            "Phosphoric Acid | ICL Group",
            "ICL Group is a leading producer of phosphoric acid.",
        ),
        _result(
            "https://unmatched.example/product",
            "Phosphoric acid product",
            "Product specifications without an identified company role.",
        ),
    ]

    report = build_company_classification_report("phosphoric_acid", results)

    rows = report["results"]
    assert isinstance(rows, list)
    assert len(rows) == len(results)
    assert all(row["entity_classifications"] for row in rows)
    icl = rows[0]["entity_classifications"][0]
    assert icl["role"] == "MANUFACTURER"
    assert icl["detailed_classification"] == "PROBABLE_MANUFACTURER"
    assert icl["evidence"][0]["source_url"] == results[0].url
    assert "ICL Group is a leading producer" in icl["evidence"][0][
        "evidence_excerpt"
    ]
    assert rows[1]["entity_classifications"][0]["role"] == "UNKNOWN"
    assert rows[1]["entity_classifications"][0]["evidence"] == []


def test_ground_truth_comparison_counts_hits_errors_and_missing_entities() -> None:
    report = build_company_classification_report(
        "phosphoric_acid",
        [
            _result(
                "https://www.icl-group.com/phosphoric-acid",
                "Phosphoric Acid | ICL Group",
                "ICL Group is a leading producer of phosphoric acid.",
            ),
            _result(
                "https://gjchemical.com/phosphoric-acid",
                "GJ Chemical phosphoric acid",
                "GJ Chemical is a supplier and distributor of phosphoric acid.",
            ),
            _result(
                "https://mahaco.biz/phosphoric-acid",
                "Zhengzhou MAHACO Industrial Co., Ltd",
                "Zhengzhou MAHACO Industrial Co., Ltd is a trading company.",
            ),
            _result(
                "https://cobasegroup.com/phosphoric-acid",
                "Cobase Group phosphoric acid",
                "Cobase Group is a manufacturer of phosphoric acid.",
            ),
        ],
    )

    comparison = report["ground_truth_comparison"]
    assert comparison["summary"] == {
        "hits": 3,
        "errors": 1,
        "not_found": 3,
        "evaluated": 4,
    }
    rows = _entity_rows(report)
    assert rows["icl_group"]["comparison"] == "HIT"
    assert rows["gj_chemical"]["classification"] == "DISTRIBUTOR"
    assert rows["zhengzhou_mahaco_industrial"]["classification"] == "TRADER"
    assert rows["cobase_group"]["comparison"] == "ERROR"


def test_false_positive_count_covers_every_result_not_only_entity_summary() -> None:
    report = build_company_classification_report(
        "phosphoric_acid",
        [
            _result(
                "https://gjchemical.com/phosphoric-acid",
                "GJ Chemical phosphoric acid manufacturer",
                "GJ Chemical is a manufacturer of phosphoric acid.",
            ),
            _result(
                "https://unadjudicated.example/product",
                "Unadjudicated manufacturer",
                "Unadjudicated is a manufacturer of phosphoric acid.",
            ),
        ],
    )

    summary = report["result_error_summary"]
    assert summary["scope"] == "ALL_RESULTS"
    assert summary["total_results"] == 2
    assert summary["errors"] == 1
    assert summary["false_positive_errors"] == 1
    assert summary["not_adjudicated"] == 1
    assert summary["non_unknown_not_adjudicated"] == 1


def test_directory_negative_is_not_manufacturer_from_list_heading() -> None:
    report = build_company_classification_report(
        "phosphoric_acid",
        [
            _result(
                "https://us.metoree.com/categories/6558",
                "16 Phosphoric Acid Manufacturers in 2026",
                "This page contains a list of phosphoric acid manufacturers.",
            )
        ],
    )

    rows = _entity_rows(report)
    negative = rows["metoree_directory"]
    assert negative["classification"] == "UNKNOWN"
    assert negative["negative_behavior"] == "SAFE"
    assert report["ground_truth_comparison"]["negative"] == {
        "appeared": True,
        "violations": 0,
        "behavior": "PASS",
    }


def test_unrelated_testimonial_role_is_not_attributed_to_distributor() -> None:
    report = build_company_classification_report(
        "phosphoric_acid",
        [
            _result(
                "https://gjchemical.com/phosphoric-acid",
                "GJ Chemical phosphoric acid",
                (
                    "Manufacturer testimonial about delivery. "
                    + ("Customer feedback. " * 20)
                    + "GJ Chemical is a supplier and distributor of phosphoric acid."
                ),
            )
        ],
    )

    rows = _entity_rows(report)
    assert rows["gj_chemical"]["classification"] == "DISTRIBUTOR"
    assert {
        evidence["supports"] for evidence in rows["gj_chemical"]["evidence"]
    } == {"explicit_distribution_evidence"}


def test_ground_truth_role_does_not_create_classification_evidence() -> None:
    report = build_company_classification_report(
        "phosphoric_acid",
        [
            _result(
                "https://www.icl-group.com/phosphoric-acid",
                "Phosphoric Acid | ICL Group",
                "Phosphoric acid specifications only.",
            )
        ],
    )

    rows = _entity_rows(report)
    assert rows["icl_group"]["ground_truth_role"] == "MANUFACTURER"
    assert rows["icl_group"]["classification"] == "UNKNOWN"
    assert rows["icl_group"]["comparison"] == "ERROR"
    assert rows["icl_group"]["evidence"] == []


def test_negative_preserves_exact_granular_must_not_be_rule() -> None:
    report = build_company_classification_report(
        "titanium_dioxide",
        [
            _result(
                "https://third-party.example/r6618",
                "Qingdao Lidayouxuan R6618",
                "Qingdao Lidayouxuan is described as a titanium dioxide manufacturer.",
            )
        ],
    )

    rows = _entity_rows(report)
    negative = rows["qingdao_lidayouxuan"]
    assert negative["detailed_classification"] == "PROBABLE_MANUFACTURER"
    assert negative["must_not_be"] == ["VERIFIED_MANUFACTURER"]
    assert negative["negative_behavior"] == "SAFE"
