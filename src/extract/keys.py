from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def extract_storage_key(
    provider_name: str,
    urls: list[str],
    depth: str,
    request_parameters: Mapping[str, Any] | None = None,
) -> str:
    serialized = json.dumps(
        {
            "provider": provider_name,
            "request": {
                "urls": urls,
                "extract_depth": depth,
                **dict(request_parameters or {}),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
