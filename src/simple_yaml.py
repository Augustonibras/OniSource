from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _parse_scalar(value: str) -> str | int | float | bool | None:
    if value.startswith('"') and value.endswith('"'):
        return json.loads(value)
    if value in {"true", "false", "null"}:
        return json.loads(value)
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _parse_yaml_block(
    lines: list[tuple[int, str]], start: int, indent: int
) -> tuple[dict[str, Any] | list[Any], int]:
    is_list = lines[start][1].startswith("- ")
    result: dict[str, Any] | list[Any] = [] if is_list else {}
    index = start

    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent:
            raise ValueError("invalid YAML indentation")

        if is_list:
            if not content.startswith("- "):
                raise ValueError("mixed YAML collection types")
            assert isinstance(result, list)
            result.append(_parse_scalar(content[2:].strip()))
            index += 1
            continue

        if content.startswith("- ") or ":" not in content:
            raise ValueError("invalid YAML mapping entry")
        assert isinstance(result, dict)
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            index += 1
            continue

        index += 1
        if index >= len(lines) or lines[index][0] <= indent:
            result[key] = {}
            continue
        child_indent = lines[index][0]
        child, index = _parse_yaml_block(lines, index, child_indent)
        result[key] = child

    return result, index


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as yaml_file:
        lines = [
            (len(raw_line) - len(raw_line.lstrip(" ")), raw_line.strip())
            for raw_line in yaml_file
            if raw_line.strip() and not raw_line.lstrip().startswith("#")
        ]
    if not lines:
        return {}
    parsed, end = _parse_yaml_block(lines, 0, lines[0][0])
    if end != len(lines) or not isinstance(parsed, dict):
        raise ValueError("YAML must contain one mapping")
    return parsed
