from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Mapping


DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "query_templates.yaml"
)
QUERY_SET_VERSION = "phase0-search-v2"
MAX_QUERIES_PER_CASE = 16
_TEMPLATE_SECTIONS = (
    "base_templates",
    "category_templates",
    "cas_templates",
    "origin_templates",
    "market_templates",
)
_SECTION_PLACEHOLDERS = {
    "base_templates": {"product_name"},
    "category_templates": {"category"},
    "cas_templates": {"cas_number"},
    "origin_templates": {"category", "country"},
    "market_templates": {"product_name", "category"},
}
_ALLOWED_ROLE_TERMS = {
    "alternative",
    "distribuidor brasil",
    "equivalent",
    "fornecedor brasil",
    "manufacturer",
    "producer",
    "producers list",
    "revendedor brasil",
    "technical data sheet",
    "supplier",
}
_BRANDED_ONLY_ROLE_TERMS = {"equivalent", "alternative"}
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
        _validate_template(
            template,
            section=current_section,
            line_number=line_number,
        )
        sections[current_section].append(template)

    if not sections["base_templates"]:
        raise QueryTemplateError("At least one base query template is required")
    return sections


def _validate_template(
    template: str,
    *,
    section: str,
    line_number: int,
) -> None:
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
        if (
            field_name not in _SECTION_PLACEHOLDERS[section]
            or format_spec
            or conversion
        ):
            raise QueryTemplateError(
                f"Unsupported template field at line {line_number}"
            )
        fields.append(field_name)

    if not fields:
        raise QueryTemplateError(
            f"Template at line {line_number} must use an allowed placeholder"
        )
    fixed_text = " ".join("".join(literal_parts).split()).casefold()
    if fixed_text not in _ALLOWED_ROLE_TERMS:
        raise QueryTemplateError(
            f"Template at line {line_number} contains a non-role search term"
        )


def _template_fixed_text(template: str) -> str:
    literal_parts = [
        literal_text
        for literal_text, _, _, _ in string.Formatter().parse(template)
    ]
    return " ".join("".join(literal_parts).split()).casefold()


def _validate_resolved_product_name(product_name: str) -> str:
    normalized = " ".join(product_name.split())
    if not normalized:
        raise ValueError("product_name is required")
    if _INTERNAL_MP_CODE.search(normalized) or _BARE_INTERNAL_CODE.fullmatch(normalized):
        raise InternalMPCodeError(
            "Internal MP codes cannot be used as external query product names"
        )
    return normalized


def _configured_cas_numbers(
    category_config: Mapping[str, object] | None,
) -> list[str]:
    if category_config is None:
        return []

    singular = category_config.get("cas_number")
    plural = category_config.get("cas_numbers")
    if singular is not None and plural is not None:
        raise ValueError("category cannot define both cas_number and cas_numbers")

    if singular is not None:
        raw_values: list[object] = [singular]
    elif plural is not None:
        if not isinstance(plural, (list, tuple)):
            raise ValueError("category cas_numbers must be a list")
        raw_values = list(plural)
    else:
        return []

    normalized_values: list[str] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("each configured CAS number must be non-empty text")
        normalized_values.append(" ".join(raw_value.split()))
    return normalized_values


def _configured_branded(
    category_config: Mapping[str, object] | None,
) -> bool:
    if category_config is None or "branded" not in category_config:
        return False
    branded = category_config["branded"]
    if not isinstance(branded, bool):
        raise ValueError("category branded must be true or false")
    return branded


def _configured_origin_countries(
    category_config: Mapping[str, object] | None,
) -> list[str]:
    if category_config is None or "origin_countries" not in category_config:
        return []
    raw_countries = category_config["origin_countries"]
    if not isinstance(raw_countries, (list, tuple)):
        raise ValueError("category origin_countries must be a list")

    countries: list[str] = []
    for raw_country in raw_countries:
        if not isinstance(raw_country, str) or not raw_country.strip():
            raise ValueError("each configured origin country must be non-empty text")
        countries.append(" ".join(raw_country.split()))
    return countries


def _configured_category_name(
    category_config: Mapping[str, object] | None,
) -> str | None:
    if category_config is None or "category" not in category_config:
        return None
    category_name = category_config["category"]
    if not isinstance(category_name, str) or not category_name.strip():
        raise ValueError("configured category must be non-empty text")
    return " ".join(category_name.split())


def build_search_queries(
    product_name: str,
    category: str | None = None,
    *,
    category_config: Mapping[str, object] | None = None,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> list[str]:
    resolved_product_name = _validate_resolved_product_name(product_name)
    configured_category = _configured_category_name(category_config)
    normalized_category = (
        configured_category
        if configured_category is not None
        else " ".join(category.split()) if category else ""
    )
    cas_numbers = _configured_cas_numbers(category_config)
    branded = _configured_branded(category_config)
    origin_countries = _configured_origin_countries(category_config)

    templates = load_query_templates(template_path)
    values = {
        "product_name": resolved_product_name,
        "category": normalized_category,
        "cas_number": "",
        "country": "",
    }

    rendered: list[str] = []
    for section in _TEMPLATE_SECTIONS:
        if section == "category_templates" and not normalized_category:
            continue
        if section == "cas_templates" and not cas_numbers:
            continue
        if section == "origin_templates" and not origin_countries:
            continue
        for template in templates[section]:
            if (
                section == "base_templates"
                and _template_fixed_text(template) in _BRANDED_ONLY_ROLE_TERMS
                and not branded
            ):
                continue
            required_fields = {
                field_name
                for _, field_name, _, _ in string.Formatter().parse(template)
                if field_name is not None
            }
            contexts = [values]
            if section == "cas_templates":
                contexts = [
                    {**values, "cas_number": cas_number}
                    for cas_number in cas_numbers
                ]
            elif section == "origin_templates":
                contexts = [
                    {**values, "country": country}
                    for country in origin_countries
                ]
            for context in contexts:
                if any(not context[field_name] for field_name in required_fields):
                    continue
                rendered.append(" ".join(template.format(**context).split()))

    unique_queries: list[str] = []
    seen: set[str] = set()
    for query in rendered:
        deduplication_key = " ".join(query.split()).casefold()
        if deduplication_key in seen:
            continue
        seen.add(deduplication_key)
        unique_queries.append(query)

    if len(unique_queries) > MAX_QUERIES_PER_CASE:
        raise QueryLimitExceededError(
            f"Query plan contains {len(unique_queries)} unique queries; "
            f"maximum is {MAX_QUERIES_PER_CASE}"
        )
    return unique_queries
