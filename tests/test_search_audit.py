from __future__ import annotations

import json

import pytest

from src.search.audit import (
    CassetteOverwriteError,
    RunRecorder,
    freeze_run_as_cassette,
)
from src.search.cassette import CassetteSearchProvider


def test_reviewed_run_can_be_frozen_and_replayed(tmp_path) -> None:
    recorder = RunRecorder(tmp_path / "runs")
    response_path = recorder.record_success(
        provider="tavily",
        query="phosphoric acid manufacturer",
        search_depth="advanced",
        max_results=10,
        retrieved_at="2026-08-19T12:00:00Z",
        raw_response={
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "content": "snippet",
                    "raw_content": "full content",
                    "score": 0.8,
                }
            ]
        },
        charged_credits=2,
        execution_credits=2,
        monthly_credits=2,
    )

    cassette_path = freeze_run_as_cassette(
        response_path,
        cassette_dir=tmp_path / "cassettes",
    )
    replayed = CassetteSearchProvider(tmp_path / "cassettes").search(
        "phosphoric acid manufacturer"
    )

    assert cassette_path.is_file()
    assert replayed[0].content == "full content"
    credit_log = json.loads(
        (response_path.parent / "credits.json").read_text(encoding="utf-8")
    )
    assert credit_log["charged_credits"] == 2
    assert credit_log["retries"] == 0
    assert credit_log["error_counts"] == {}


def test_existing_cassette_requires_explicit_refresh(tmp_path) -> None:
    recorder = RunRecorder(tmp_path / "runs")
    response_path = recorder.record_success(
        provider="tavily",
        query="test query",
        search_depth="advanced",
        max_results=10,
        retrieved_at="2026-08-19T12:00:00Z",
        raw_response={"results": []},
        charged_credits=2,
        execution_credits=2,
        monthly_credits=2,
    )
    cassette_dir = tmp_path / "cassettes"
    freeze_run_as_cassette(response_path, cassette_dir=cassette_dir)

    with pytest.raises(CassetteOverwriteError, match="--refresh-cassettes"):
        freeze_run_as_cassette(response_path, cassette_dir=cassette_dir)

    refreshed = freeze_run_as_cassette(
        response_path,
        cassette_dir=cassette_dir,
        refresh_cassettes=True,
    )
    assert refreshed.is_file()
