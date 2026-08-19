from __future__ import annotations

import hashlib
import json


def search_storage_key(
    provider_name: str,
    query: str,
    depth: str,
    max_results: int,
) -> str:
    serialized = json.dumps(
        [provider_name, query, depth, max_results],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
