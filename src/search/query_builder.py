from __future__ import annotations

import json
import re
import string
from pathlib import Path


DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "query_templates.yaml"
)
MAX_QUERIES_PER_CASE = 12
_TEMPLATE_SECTIONS = {"base_templates", "category_templates"}
_ALLOWED_PLACEHOLDERS = {"product_name", "category"}
_ALLOWED_ROLE_TERMS = {
    "manufacturer",
    "producer",
    "technical data sheet",
    "supplier",
    "cas",
}
_INTERNAL_MP_CODE = re.compile(r"\bMP\s*\d{1,3}\b", re.IGNORECASE)
_BARE_INTERNAL_CODE = re.compile(r"^\d{1,3}$")


class QueryTemplateError(ValueError):
    """Raised when query template configuration is invalid."""


class QueryLimitExceededError(ValueError):
    """Raised instead of silently truncating an oversized query plan."""


class InternalMPCodeError(ValueError):
    """Raised when an internal MP code reaches the external-query boundary."""


def _unquote_yaml_scalar(value: str, *, line_number: int) -> str:
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        raise QueryTemplateError(
            f"Query template at line {line_number} must be double quoted"
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise QueryTemplateError(
            f"Invalid quoted template at line {line_number}"
        ) from error
    if not isinstance(parsed, str):
        raise QueryTemplateError(f"Template at line {line_number} must be text")
    return parsed


def load_query_templates(
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> dict[str, list[str]]:
    path = Path(template_path)
    sections = {name: [] for name in _TEMPLATE_SECTIONS}
    current_section: str | None = None

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise QueryTemplateError(f"Could not read query templates: {path}") from error

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith(" ") and stripped.endswith(":"):
            current_section = stripped[:-1]
            if current_section not in _TEMPLATE_SECTIONS:
                raise QueryTemplateError(
                    f"Unknown query template section at line {line_number}"
                )
            continue
        if current_section is None or not raw_line.startswith("  - "):
            raise QueryTemplateError(f"Invalid query template YAML at line {line_number}")
        template = _unquote_yaml_scalar(
            raw_line[len("  - ") :].strip(),
            line_number=line_number,
        )
        _validate_template(template, line_number=line_number)
        sections[current_section].append(template)

    if not sections["base_templates"]:
        raise QueryTemplateError("At least one base query template is required")
    return sections


def _validate_template(template: str, *, line_number: int) -> None:
    formatter = string.Formatter()
    fields: list[str] = []
    literal_parts: list[str] = []
    try:
        parsed = list(formatter.parse(template))
    except ValueError as error:
        raise QueryTemplateError(f"Invalid template at line {line_number}") from error

    for literal_text, field_name, format_spec, conversion in parsed:
        literal_parts.append(literal_text)
        if field_name is None:
            continue
        if field_name not in _ALLOWED_PLACEHOLDERS or format_spec or conversion:
            raise QueryTemplateError(
                f"Unsupported template field at line {line_number}"
            )
        fields.append(field_name)

    if "product_name" not in fields:
        raise QueryTemplateError(
            f"Template at line {line_number} must use product_name"
        )
    fixed_text = " ".join("".join(literal_parts).split()).casefold()
    if fixed_text not in _ALLOWED_ROLE_TERMS:
        raise QueryTemplateError(
            f"Template at line {line_number} contains a non-role search term"
        )


def _validate_resolved_product_name(product_name: str) -> str:
    normalized = " ".join(product_name.split())
    if not normalized:
        raise ValueError("product_name is required")
    if _INTERNAL_MP_CODE.search(normalized) or _BARE_INTERNAL_CODE.fullmatch(normalized):
        raise InternalMPCodeError(
            "Internal MP codes cannot be used as external query product names"
        )
    return normalized


def build_search_queries(
    product_name: str,
    category: str | None = None,
    *,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> list[str]:
    resolved_product_name = _validate_resolved_product_name(product_name)
    normalized_category = " ".join(category.split()) if category else ""
    templates = load_query_templates(template_path)
    selected = list(templates["base_templates"])
    if normalized_category:
        selected.extend(templates["category_templates"])

    if len(selected) > MAX_QUERIES_PER_CASE:
        raise QueryLimitExceededError(
            f"Query plan contains {len(selected)} queries; "
            f"maximum is {MAX_QUERIES_PER_CASE}"
        )

    queries = [
        " ".join(
            template.format(
                product_name=resolved_product_name,
                category=normalized_category,
            ).split()
        )
        for template in selected
    ]
    if len(set(queries)) != len(queries):
        raise QueryTemplateError("Query templates generated duplicate queries")
    return queries
