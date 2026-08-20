from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .keys import search_storage_key
from .query_builder import QUERY_SET_VERSION


DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_CASSETTES_DIR = Path("cassettes")


class AuditWriteError(OSError):
    """Raised when a live response or its credit log cannot be preserved."""


class CassetteOverwriteError(FileExistsError):
    """Raised when cassette replacement lacks explicit human refresh intent."""


class RunRecorder:
    def __init__(self, runs_dir: str | Path = DEFAULT_RUNS_DIR) -> None:
        self.runs_dir = Path(runs_dir)

    def record_success(
        self,
        *,
        provider: str,
        query: str,
        search_depth: str,
        max_results: int,
        retrieved_at: str,
        raw_response: dict[str, Any],
        charged_credits: int,
        execution_credits: int,
        monthly_credits: int,
        retries: int = 0,
        error_counts: dict[str, int] | None = None,
        request_parameters: Mapping[str, Any] | None = None,
    ) -> Path:
        storage_key = search_storage_key(
            provider,
            query,
            search_depth,
            max_results,
            request_parameters,
        )
        timestamp = retrieved_at.replace(":", "").replace("-", "").replace(".", "")
        run_dir = self.runs_dir / f"{timestamp}_{storage_key[:12]}"
        response_path = run_dir / "response.json"
        credits_path = run_dir / "credits.json"
        envelope = {
            "provider": provider,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "request_parameters": dict(request_parameters or {}),
            "retrieved_at": retrieved_at,
            "response": raw_response,
        }
        credit_log = {
            "charged_credits": charged_credits,
            "execution_credits": execution_credits,
            "monthly_credits": monthly_credits,
            "retries": retries,
            "error_counts": error_counts or {},
        }

        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            response_path.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            credits_path.write_text(
                json.dumps(credit_log, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise AuditWriteError(f"Could not record live search run: {run_dir}") from error
        return response_path

    def record_failure(
        self,
        *,
        provider: str,
        query: str,
        search_depth: str,
        max_results: int,
        retrieved_at: str,
        error_type: str,
        charged_credits: int,
        execution_credits: int,
        monthly_credits: int,
        retries: int,
        error_counts: dict[str, int],
        request_parameters: Mapping[str, Any] | None = None,
    ) -> Path:
        storage_key = search_storage_key(
            provider,
            query,
            search_depth,
            max_results,
            request_parameters,
        )
        timestamp = retrieved_at.replace(":", "").replace("-", "").replace(".", "")
        run_dir = self.runs_dir / f"{timestamp}_{storage_key[:12]}"
        error_path = run_dir / "error.json"
        credits_path = run_dir / "credits.json"
        error_log = {
            "provider": provider,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "request_parameters": dict(request_parameters or {}),
            "retrieved_at": retrieved_at,
            "error_type": error_type,
        }
        credit_log = {
            "charged_credits": charged_credits,
            "execution_credits": execution_credits,
            "monthly_credits": monthly_credits,
            "retries": retries,
            "error_counts": error_counts,
        }

        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            error_path.write_text(
                json.dumps(error_log, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            credits_path.write_text(
                json.dumps(credit_log, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise AuditWriteError(f"Could not record failed search run: {run_dir}") from error
        return error_path


def freeze_run_as_cassette(
    run_response_path: str | Path,
    *,
    cassette_dir: str | Path = DEFAULT_CASSETTES_DIR,
    refresh_cassettes: bool = False,
    query_set_version: str = QUERY_SET_VERSION,
) -> Path:
    source = Path(run_response_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditWriteError(f"Could not read run response: {source}") from error
    if not isinstance(payload, dict):
        raise AuditWriteError("Run response must contain a JSON object")

    required = (
        "provider",
        "query",
        "search_depth",
        "max_results",
        "request_parameters",
        "retrieved_at",
        "response",
    )
    if any(field_name not in payload for field_name in required):
        raise AuditWriteError("Run response is missing cassette metadata")
    return _write_cassette_payload(
        payload,
        cassette_dir=Path(cassette_dir),
        refresh_cassettes=refresh_cassettes,
        query_set_version=query_set_version,
    )


def freeze_cache_as_cassette(
    cache_path: str | Path,
    *,
    cassette_dir: str | Path = DEFAULT_CASSETTES_DIR,
    refresh_cassettes: bool = False,
    query_set_version: str = QUERY_SET_VERSION,
) -> Path:
    source = Path(cache_path)
    try:
        cache_payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditWriteError(f"Could not read search cache: {source}") from error
    required = (
        "provider",
        "query",
        "search_depth",
        "max_results",
        "request_parameters",
        "retrieved_at",
        "response",
    )
    if (
        not isinstance(cache_payload, dict)
        or cache_payload.get("format") != "raw_provider_response"
        or any(field_name not in cache_payload for field_name in required)
    ):
        raise AuditWriteError("Search cache is missing raw cassette metadata")
    cassette_payload = {
        field_name: cache_payload[field_name]
        for field_name in required
    }
    return _write_cassette_payload(
        cassette_payload,
        cassette_dir=Path(cassette_dir),
        refresh_cassettes=refresh_cassettes,
        query_set_version=query_set_version,
    )


def _write_cassette_payload(
    payload: dict[str, Any],
    *,
    cassette_dir: Path,
    refresh_cassettes: bool,
    query_set_version: str,
) -> Path:
    key = search_storage_key(
        payload["provider"],
        payload["query"],
        payload["search_depth"],
        payload["max_results"],
        payload["request_parameters"],
    )
    target = cassette_dir / f"{key}.json"
    if target.exists() and not refresh_cassettes:
        raise CassetteOverwriteError(
            f"Cassette already exists; use --refresh-cassettes to replace it: {target}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target.with_suffix(target.suffix + ".tmp")
    cassette_payload = {
        **payload,
        "captured_at": payload["retrieved_at"],
        "query_set_version": query_set_version,
    }
    try:
        temporary_path.write_text(
            json.dumps(
                cassette_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, target)
    except OSError as error:
        raise AuditWriteError(f"Could not freeze cassette: {target}") from error
    return target
