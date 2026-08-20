from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from src.simple_yaml import load_yaml_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADJUDICATED_RESULTS_PATH = PROJECT_ROOT / "benchmark" / "adjudicated_results.yaml"
COMMERCIAL_ROLES = ("MANUFACTURER", "DISTRIBUTOR", "TRADER")
HUMAN_LABEL_ORDER = (
    *COMMERCIAL_ROLES,
    "MARKETPLACE_OR_DIRECTORY",
    "NOT_A_COMPANY",
    "NOT_A_SUPPLIER",
    "UNCERTAIN",
)
HUMAN_LABELS = set(HUMAN_LABEL_ORDER)
PREDICTED_ROLE_COLUMNS = (
    "MANUFACTURER",
    "DISTRIBUTOR",
    "TRADER",
    "UNKNOWN",
    "NOT_A_COMPANY",
    "MARKETPLACE",
)
_PRODUCTION_SUPPORTS = {
    "production_capacity_evidence",
    "production_process_evidence",
    "own_plant_location_evidence",
    "factory_operating_years_evidence",
}


class AdjudicationError(ValueError):
    """Raised when human result adjudication cannot be loaded deterministically."""


@dataclass(frozen=True, slots=True)
class AdjudicatedResult:
    case: str
    category: str
    domain: str
    url: str
    human_label: str


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicationError(f"adjudication {field_name} must be non-empty text")
    return value.strip()


def _normalized_domain(value: str) -> str:
    return value.strip().casefold().rstrip(".")


def load_adjudicated_results(category: str) -> tuple[AdjudicatedResult, ...]:
    payload = load_yaml_mapping(ADJUDICATED_RESULTS_PATH)
    if payload.get("version") != 1 or payload.get("source") != "HUMAN":
        raise AdjudicationError("adjudication metadata must be version 1 and HUMAN")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, dict):
        raise AdjudicationError("adjudication cases must be a mapping")

    normalized_category = "_".join(category.casefold().replace("_", " ").split())
    loaded: list[AdjudicatedResult] = []
    seen_urls: set[str] = set()
    for raw_case, raw_case_payload in raw_cases.items():
        case = _required_text(raw_case, field_name="case")
        if not isinstance(raw_case_payload, dict):
            raise AdjudicationError(f"adjudication case {case} must be a mapping")
        case_category = _required_text(
            raw_case_payload.get("category"),
            field_name=f"case {case} category",
        )
        if case_category != normalized_category:
            continue
        raw_results = raw_case_payload.get("results")
        if not isinstance(raw_results, dict):
            raise AdjudicationError(
                f"adjudication case {case} results must be a mapping"
            )
        for raw_domain, raw_result in raw_results.items():
            domain = _normalized_domain(
                _required_text(raw_domain, field_name=f"case {case} domain")
            )
            if not isinstance(raw_result, dict):
                raise AdjudicationError(
                    f"adjudication result {domain} must be a mapping"
                )
            url = _required_text(
                raw_result.get("url"), field_name=f"{domain} url"
            )
            returned_domain = _normalized_domain(urlsplit(url).hostname or "")
            if returned_domain != domain:
                raise AdjudicationError(
                    f"adjudication domain does not match URL: {domain}"
                )
            human_label = _required_text(
                raw_result.get("human_label"),
                field_name=f"{domain} human_label",
            )
            if human_label not in HUMAN_LABELS:
                raise AdjudicationError(
                    f"unsupported human adjudication label: {human_label}"
                )
            if url in seen_urls:
                raise AdjudicationError(f"duplicate adjudicated URL: {url}")
            seen_urls.add(url)
            loaded.append(
                AdjudicatedResult(
                    case=case,
                    category=case_category,
                    domain=domain,
                    url=url,
                    human_label=human_label,
                )
            )
    return tuple(loaded)


def _percentage(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return "NOT_DEFINED"
    return round(numerator / denominator * 100, 2)


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _manufacturer_blocking_gates(
    classification: Mapping[str, object],
) -> list[str]:
    predicted = classification.get("role")
    if predicted == "MANUFACTURER":
        return []
    reason_codes = _text_list(classification.get("reason_codes"))
    page_type = classification.get("page_type")
    if isinstance(page_type, str) and page_type != "COMPANY":
        noncommercial = [
            code for code in reason_codes if code.startswith("PAGE_TYPE_")
        ]
        return noncommercial or [f"PAGE_TYPE_{page_type}_NON_COMMERCIAL"]

    forced_trader = [
        code
        for code in reason_codes
        if code
        in {
            "THIRD_PARTY_BRAND_SALE_AUTOMATIC_TRADER",
            "BROAD_UNRELATED_CHEMICAL_CATALOG_AUTOMATIC_TRADER",
        }
    ]
    if forced_trader:
        return forced_trader

    raw_evidence = classification.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, list) else []
    supports = {
        item.get("supports")
        for item in evidence
        if isinstance(item, Mapping) and isinstance(item.get("supports"), str)
    }
    if "explicit_manufacturing_evidence" not in supports:
        return ["EXPLICIT_MANUFACTURING_EVIDENCE_REQUIRED"]
    if not supports.intersection(_PRODUCTION_SUPPORTS):
        return ["MANUFACTURER_POSITIVE_PRODUCTION_SIGNAL_REQUIRED"]
    return reason_codes or [f"PREDICTED_ROLE_{predicted}_BLOCKED_MANUFACTURER"]


def _evaluation_metrics(
    comparisons: list[dict[str, object]],
) -> dict[str, object]:
    precision_by_role: dict[str, dict[str, object]] = {}
    recall_by_role: dict[str, dict[str, object]] = {}
    for role in COMMERCIAL_ROLES:
        predicted_rows = [
            row for row in comparisons if row["predicted_role"] == role
        ]
        correct_precision = sum(
            row["human_label"] == role for row in predicted_rows
        )
        predicted_count = len(predicted_rows)
        precision_by_role[role] = {
            "correct": correct_precision,
            "predicted": predicted_count,
            "false_positives": predicted_count - correct_precision,
            "precision_percentage": _percentage(
                correct_precision,
                predicted_count,
            ),
        }

        human_rows = [row for row in comparisons if row["human_label"] == role]
        correct_recall = sum(row["predicted_role"] == role for row in human_rows)
        human_count = len(human_rows)
        recall_by_role[role] = {
            "correct": correct_recall,
            "human_total": human_count,
            "false_negatives": human_count - correct_recall,
            "recall_percentage": _percentage(correct_recall, human_count),
        }

    matrix = {
        human_label: {predicted: 0 for predicted in PREDICTED_ROLE_COLUMNS}
        for human_label in HUMAN_LABEL_ORDER
    }
    for row in comparisons:
        human_label = row["human_label"]
        predicted = row["predicted_role"]
        if human_label in matrix and predicted in PREDICTED_ROLE_COLUMNS:
            matrix[human_label][predicted] += 1

    blocked_manufacturers = [
        {
            "domain": row["domain"],
            "url": row["url"],
            "predicted_role": row["predicted_role"],
            "blocking_gates": row["manufacturer_blocking_gates"],
        }
        for row in comparisons
        if row["human_label"] == "MANUFACTURER"
        and row["predicted_role"] != "MANUFACTURER"
    ]
    return {
        "precision_by_role": precision_by_role,
        "recall_by_role": recall_by_role,
        "confusion_matrix": {
            "rows": list(HUMAN_LABEL_ORDER),
            "columns": list(PREDICTED_ROLE_COLUMNS),
            "values": matrix,
        },
        "blocked_manufacturers": blocked_manufacturers,
    }


def evaluate_adjudicated_results(
    category: str,
    result_rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Measure predictions against human result labels without feeding labels back."""

    adjudicated = load_adjudicated_results(category)
    indexed: dict[str, Mapping[str, object]] = {}
    for row in result_rows:
        raw_url = row.get("url")
        if isinstance(raw_url, str):
            indexed.setdefault(raw_url, row)

    comparisons: list[dict[str, object]] = []
    missing = 0
    for item in adjudicated:
        row = indexed.get(item.url)
        if row is None:
            missing += 1
            comparisons.append(
                {
                    "domain": item.domain,
                    "url": item.url,
                    "human_label": item.human_label,
                    "predicted_role": "NOT_FOUND",
                    "comparison": "NOT_FOUND",
                    "manufacturer_blocking_gates": (
                        ["RESULT_NOT_FOUND"]
                        if item.human_label == "MANUFACTURER"
                        else []
                    ),
                }
            )
            continue
        classification = row.get("domain_classification")
        if not isinstance(classification, Mapping):
            raise AdjudicationError("result domain_classification must be a mapping")
        predicted = classification.get("role")
        if not isinstance(predicted, str):
            raise AdjudicationError("result role must be text")
        comparisons.append(
            {
                "domain": item.domain,
                "url": item.url,
                "human_label": item.human_label,
                "predicted_role": predicted,
                "comparison": "HIT" if predicted == item.human_label else "ERROR",
                "manufacturer_blocking_gates": (
                    _manufacturer_blocking_gates(classification)
                    if item.human_label == "MANUFACTURER"
                    else []
                ),
            }
        )

    metrics = _evaluation_metrics(comparisons)

    return {
        "scope": "HUMAN_ADJUDICATED_RESULTS",
        "adjudicated": len(adjudicated),
        "matched": len(adjudicated) - missing,
        "missing": missing,
        **metrics,
        "results": comparisons,
    }


def aggregate_adjudicated_precision(
    evaluations: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Aggregate per-case adjudicated precision without changing its denominator."""

    totals = {
        role: {"correct": 0, "predicted": 0, "false_positives": 0}
        for role in COMMERCIAL_ROLES
    }
    for evaluation in evaluations:
        raw_roles = evaluation.get("precision_by_role")
        if not isinstance(raw_roles, Mapping):
            raise AdjudicationError("precision_by_role must be a mapping")
        for role in COMMERCIAL_ROLES:
            raw_stats = raw_roles.get(role)
            if not isinstance(raw_stats, Mapping):
                raise AdjudicationError(f"precision stats missing for {role}")
            for field in ("correct", "predicted", "false_positives"):
                value = raw_stats.get(field)
                if not isinstance(value, int):
                    raise AdjudicationError(f"precision {role} {field} must be integer")
                totals[role][field] += value

    return {
        role: {
            **stats,
            "precision_percentage": _percentage(
                stats["correct"],
                stats["predicted"],
            ),
        }
        for role, stats in totals.items()
    }


def aggregate_adjudicated_evaluations(
    evaluations: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Combine case-level adjudication metrics and confusion counts."""

    items = list(evaluations)
    combined_results: list[dict[str, object]] = []
    for evaluation in items:
        raw_results = evaluation.get("results")
        if not isinstance(raw_results, list):
            raise AdjudicationError("adjudication results must be a list")
        for row in raw_results:
            if not isinstance(row, dict):
                raise AdjudicationError("adjudication result row must be a mapping")
            combined_results.append(row)
    metrics = _evaluation_metrics(combined_results)
    return {
        "scope": "COMBINED_HUMAN_ADJUDICATED_RESULTS",
        "adjudicated": sum(
            value
            for evaluation in items
            for value in [evaluation.get("adjudicated")]
            if isinstance(value, int)
        ),
        "matched": sum(
            value
            for evaluation in items
            for value in [evaluation.get("matched")]
            if isinstance(value, int)
        ),
        "missing": sum(
            value
            for evaluation in items
            for value in [evaluation.get("missing")]
            if isinstance(value, int)
        ),
        **metrics,
    }
