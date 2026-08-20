from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from src.simple_yaml import load_yaml_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADJUDICATED_RESULTS_PATH = PROJECT_ROOT / "benchmark" / "adjudicated_results.yaml"
COMMERCIAL_ROLES = ("MANUFACTURER", "DISTRIBUTOR", "TRADER")
HUMAN_LABELS = {
    *COMMERCIAL_ROLES,
    "MARKETPLACE_OR_DIRECTORY",
    "NOT_A_COMPANY",
    "NOT_A_SUPPLIER",
    "UNCERTAIN",
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
            }
        )

    precision_by_role: dict[str, dict[str, object]] = {}
    for role in COMMERCIAL_ROLES:
        predicted_rows = [
            row for row in comparisons if row["predicted_role"] == role
        ]
        correct = sum(row["human_label"] == role for row in predicted_rows)
        predicted_count = len(predicted_rows)
        precision_by_role[role] = {
            "correct": correct,
            "predicted": predicted_count,
            "false_positives": predicted_count - correct,
            "precision_percentage": _percentage(correct, predicted_count),
        }

    return {
        "scope": "HUMAN_ADJUDICATED_RESULTS",
        "adjudicated": len(adjudicated),
        "matched": len(adjudicated) - missing,
        "missing": missing,
        "precision_by_role": precision_by_role,
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
