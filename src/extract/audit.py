from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.search.audit import AuditWriteError, CassetteOverwriteError

from .cassette import EXTRACT_SET_VERSION
from .keys import extract_storage_key


class ExtractRunRecorder:
    def __init__(self, runs_dir: str | Path = Path("runs") / "extract") -> None:
        self.runs_dir = Path(runs_dir)

    def record(
        self,
        *,
        provider: str,
        urls: list[str],
        extract_depth: str,
        request_parameters: dict[str, Any],
        retrieved_at: str,
        raw_response: dict[str, Any] | None,
        charged_credits: int,
        execution_credits: int,
        monthly_credits: int,
        retries: int,
        error_counts: dict[str, int],
        error_type: str | None = None,
    ) -> Path:
        key = extract_storage_key(
            provider,
            urls,
            extract_depth,
            request_parameters,
        )
        timestamp = retrieved_at.replace(":", "").replace("-", "").replace(".", "")
        run_dir = self.runs_dir / f"{timestamp}_{key[:12]}"
        response_path = run_dir / ("response.json" if error_type is None else "error.json")
        envelope: dict[str, Any] = {
            "provider": provider,
            "urls": urls,
            "extract_depth": extract_depth,
            "request_parameters": request_parameters,
            "retrieved_at": retrieved_at,
        }
        if error_type is None:
            envelope["response"] = raw_response
        else:
            envelope["error_type"] = error_type
        credit_log = {
            "charged_credits": charged_credits,
            "execution_credits": execution_credits,
            "monthly_credits": monthly_credits,
            "retries": retries,
            "error_counts": error_counts,
        }
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            response_path.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (run_dir / "credits.json").write_text(
                json.dumps(credit_log, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise AuditWriteError(
                f"Could not record live extraction run: {run_dir}"
            ) from error
        return response_path


def freeze_extract_cache_as_cassette(
    cache_path: str | Path,
    *,
    cassette_dir: str | Path = Path("cassettes") / "extract",
    refresh_cassettes: bool = False,
    extract_set_version: str = EXTRACT_SET_VERSION,
) -> Path:
    source = Path(cache_path)
    try:
        cache_payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditWriteError(f"Could not read extraction cache: {source}") from error
    required = (
        "provider",
        "urls",
        "extract_depth",
        "request_parameters",
        "retrieved_at",
    )
    if not isinstance(cache_payload, dict) or any(
        field not in cache_payload for field in required
    ):
        raise AuditWriteError("Extraction cache is missing cassette metadata")
    if cache_payload.get("format") == "raw_provider_response":
        response = cache_payload.get("response")
    elif cache_payload.get("format") == "normalized_extract_results":
        response = {
            "results": [
                {"url": item["url"], "raw_content": item["raw_content"]}
                for item in cache_payload.get("results", [])
            ],
            "failed_results": [],
        }
    else:
        raise AuditWriteError("Extraction cache format cannot be frozen")
    if not isinstance(response, dict):
        raise AuditWriteError("Extraction cache response is invalid")
    payload = {
        **{field: cache_payload[field] for field in required},
        "response": response,
        "captured_at": cache_payload["retrieved_at"],
        "extract_set_version": extract_set_version,
    }
    key = extract_storage_key(
        payload["provider"],
        payload["urls"],
        payload["extract_depth"],
        payload["request_parameters"],
    )
    target = Path(cassette_dir) / f"{key}.json"
    if target.exists() and not refresh_cassettes:
        raise CassetteOverwriteError(
            f"Cassette already exists; use --refresh-cassettes to replace it: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except OSError as error:
        raise AuditWriteError(f"Could not write extraction cassette: {target}") from error
    return target
