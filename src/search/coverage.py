from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from src.simple_yaml import load_yaml_mapping

from .models import SearchResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmark"


class GroundTruthCoverageError(ValueError):
    """Raised when human benchmark data cannot be read deterministically."""


@dataclass(frozen=True, slots=True)
class BenchmarkSource:
    path: Path
    negative: bool = False


@dataclass(frozen=True, slots=True)
class BenchmarkEntity:
    control_id: str
    name: str
    expected_role: str | None
    domains: tuple[str, ...]
    negative: bool


BENCHMARK_SOURCES = {
    "titanium_dioxide": (
        BenchmarkSource(BENCHMARK_ROOT / "r996" / "positive_controls.yaml"),
        BenchmarkSource(BENCHMARK_ROOT / "r996" / "distributor_controls.yaml"),
        BenchmarkSource(
            BENCHMARK_ROOT / "r996" / "negative_controls.yaml",
            negative=True,
        ),
    ),
    "phosphoric_acid": (
        BenchmarkSource(BENCHMARK_ROOT / "phosphoric_acid" / "controls.yaml"),
    ),
}


def _category_identifier(category: str) -> str:
    return "_".join(category.casefold().replace("_", " ").split())


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GroundTruthCoverageError(f"benchmark {field_name} must be non-empty text")
    return value.strip()


def _load_entities(category: str) -> list[BenchmarkEntity] | None:
    sources = BENCHMARK_SOURCES.get(_category_identifier(category))
    if sources is None:
        return None

    entities: list[BenchmarkEntity] = []
    for source in sources:
        payload = load_yaml_mapping(source.path)
        controls = payload.get("controls")
        if not isinstance(controls, dict):
            raise GroundTruthCoverageError(
                f"benchmark controls must be a mapping: {source.path}"
            )
        for raw_control_id, raw_control in controls.items():
            control_id = _required_text(raw_control_id, field_name="control id")
            if not isinstance(raw_control, dict):
                raise GroundTruthCoverageError(
                    f"benchmark control must be a mapping: {control_id}"
                )
            raw_name = raw_control.get("company", raw_control.get("domain"))
            name = _required_text(raw_name, field_name=f"{control_id} entity")
            raw_role = raw_control.get(
                "expected_company_role",
                raw_control.get("expected_role"),
            )
            expected_role = (
                _required_text(raw_role, field_name=f"{control_id} expected role")
                if raw_role is not None
                else None
            )
            domains: list[str] = []
            for domain_field in ("official_domain", "domain"):
                raw_domain = raw_control.get(domain_field)
                if raw_domain is not None:
                    domains.append(
                        _required_text(
                            raw_domain,
                            field_name=f"{control_id} {domain_field}",
                        )
                    )
            negative = source.negative or raw_control.get("entity_type") == "COMPANY_DIRECTORY"
            entities.append(
                BenchmarkEntity(
                    control_id=control_id,
                    name=name,
                    expected_role=expected_role,
                    domains=tuple(domains),
                    negative=negative,
                )
            )
    return entities


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().casefold().rstrip(".")
    return normalized.removeprefix("www.")


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks.casefold()).split())


def _domain_matches(returned_domain: str, expected_domain: str) -> bool:
    returned = _normalize_domain(returned_domain)
    expected = _normalize_domain(expected_domain)
    return returned == expected or returned.endswith(f".{expected}")


def _role_group(expected_role: str | None) -> str | None:
    if expected_role is None:
        return None
    if expected_role.endswith("MANUFACTURER"):
        return "manufacturer"
    if expected_role.endswith("DISTRIBUTOR"):
        return "distributor"
    return None


def build_ground_truth_coverage(
    category: str,
    results: Iterable[SearchResult],
) -> dict[str, object] | None:
    entities = _load_entities(category)
    if entities is None:
        return None

    indexed_results: list[tuple[str, str]] = []
    for result in results:
        domain = (urlsplit(result.url).hostname or "").casefold()
        searchable_name = _normalize_name(f"{domain} {result.title} {result.url}")
        indexed_results.append((domain, searchable_name))

    entity_rows: list[dict[str, object]] = []
    totals = {
        "manufacturer": {"found": 0, "total": 0},
        "distributor": {"found": 0, "total": 0},
    }
    negative_appeared = False

    for entity in entities:
        matched_by: set[str] = set()
        matched_domains: set[str] = set()
        normalized_entity_name = _normalize_name(entity.name)
        for returned_domain, searchable_name in indexed_results:
            domain_match = any(
                _domain_matches(returned_domain, expected_domain)
                for expected_domain in entity.domains
            )
            name_match = bool(
                normalized_entity_name
                and normalized_entity_name in searchable_name
            )
            if domain_match:
                matched_by.add("domain")
            if name_match:
                matched_by.add("name")
            if domain_match or name_match:
                matched_domains.add(returned_domain)

        found = bool(matched_domains)
        if entity.negative and found:
            negative_appeared = True
        role_group = _role_group(entity.expected_role)
        if not entity.negative and role_group is not None:
            totals[role_group]["total"] += 1
            if found:
                totals[role_group]["found"] += 1

        entity_rows.append(
            {
                "control_id": entity.control_id,
                "entity": entity.name,
                "ground_truth_role": entity.expected_role,
                "negative": entity.negative,
                "status": "ENCONTRADO" if found else "NÃO ENCONTRADO",
                "matched_by": sorted(matched_by),
                "matched_domains": sorted(matched_domains),
            }
        )

    return {
        "entities": entity_rows,
        "negative_appeared": negative_appeared,
        "total": (
            f"fabricantes {totals['manufacturer']['found']}/"
            f"{totals['manufacturer']['total']}, "
            f"distribuidores {totals['distributor']['found']}/"
            f"{totals['distributor']['total']}"
        ),
    }
