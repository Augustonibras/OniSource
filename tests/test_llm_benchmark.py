from __future__ import annotations

import pytest

from src.search.llm_benchmark import (
    classification_metric_slices,
    load_prompt_development_domains,
)


def _row(
    domain: str,
    human_label: str,
    predicted_role: str,
    samples: tuple[int, ...],
) -> dict[str, object]:
    return {
        "domain": domain,
        "human_label": human_label,
        "predicted_role": predicted_role,
        "samples": samples,
    }


def test_prompt_development_domains_are_loaded_from_separate_benchmark_file() -> None:
    assert load_prompt_development_domains() == frozenset(
        {
            "ereztech.com",
            "hxtio2.com",
            "camaltd.com",
            "b2bdata.aipage.com",
            "brandessenceresearch.com",
        }
    )


def test_metric_slices_separate_samples_and_exclude_prompt_development_set() -> None:
    rows = [
        _row("burned.example", "MANUFACTURER", "TRADER", (1,)),
        _row("sample1.example", "TRADER", "TRADER", (1,)),
        _row("sample2.example", "DISTRIBUTOR", "UNKNOWN", (2,)),
        _row("both.example", "NOT_A_COMPANY", "NOT_A_COMPANY", (1, 2)),
    ]

    metrics = classification_metric_slices(rows, {"burned.example"})

    assert metrics["sample_1"]["evaluated"] == 3
    assert metrics["sample_2"]["evaluated"] == 2
    assert metrics["excluding_prompt_development"]["evaluated"] == 3
    assert metrics["excluding_prompt_development"]["correct"] == 2
    assert metrics["excluding_prompt_development"]["accuracy_percentage"] == 66.67
    assert metrics["all_unique"]["confusion_matrix"]["values"]["MANUFACTURER"][
        "TRADER"
    ] == 1


def test_metric_slices_reject_unknown_taxonomy_values() -> None:
    with pytest.raises(ValueError, match="unsupported predicted role"):
        classification_metric_slices(
            [_row("example.com", "MANUFACTURER", "UNSUPPORTED", (1,))],
            set(),
        )
