from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def search_storage_key(
    provider_name: str,
    query: str,
    depth: str,
    max_results: int,
    request_parameters: Mapping[str, Any] | None = None,
) -> str:
    serialized = json.dumps(
        {
            "provider": provider_name,
            "request": {
                "query": query,
                "search_depth": depth,
                "max_results": max_results,
                **dict(request_parameters or {}),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
