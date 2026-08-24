from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from src.simple_yaml import load_yaml_mapping

from .company_classifier import SupplierRole, normalize_classifier_domain


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DEVELOPMENT_DOMAINS_PATH = (
    PROJECT_ROOT / "benchmark" / "prompt_development_domains.yaml"
)
ROLE_ORDER = tuple(role.value for role in SupplierRole)


def load_prompt_development_domains(
    path: str | Path = PROMPT_DEVELOPMENT_DOMAINS_PATH,
) -> frozenset[str]:
    payload = load_yaml_mapping(Path(path))
    raw_domains = payload.get("prompt_development_domains")
    if not isinstance(raw_domains, list) or not raw_domains:
        raise ValueError("prompt_development_domains must be a non-empty list")
    domains: list[str] = []
    for raw_domain in raw_domains:
        if not isinstance(raw_domain, str) or not raw_domain.strip():
            raise ValueError("prompt development domains must be non-empty text")
        domains.append(normalize_classifier_domain(raw_domain))
    if len(domains) != len(set(domains)):
        raise ValueError("prompt development domains must be unique")
    return frozenset(domains)


def _percentage(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return "NOT_DEFINED"
    return round(numerator / denominator * 100, 2)


def classification_metrics(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    evaluated = list(rows)
    for row in evaluated:
        human_label = row.get("human_label")
        predicted_role = row.get("predicted_role")
        if human_label not in ROLE_ORDER:
            raise ValueError(f"unsupported human label: {human_label}")
        if predicted_role not in ROLE_ORDER:
            raise ValueError(f"unsupported predicted role: {predicted_role}")

    precision_by_role: dict[str, dict[str, object]] = {}
    recall_by_role: dict[str, dict[str, object]] = {}
    for role in ROLE_ORDER:
        predicted = [row for row in evaluated if row["predicted_role"] == role]
        human = [row for row in evaluated if row["human_label"] == role]
        precision_correct = sum(row["human_label"] == role for row in predicted)
        recall_correct = sum(row["predicted_role"] == role for row in human)
        precision_by_role[role] = {
            "correct": precision_correct,
            "predicted": len(predicted),
            "precision_percentage": _percentage(precision_correct, len(predicted)),
        }
        recall_by_role[role] = {
            "correct": recall_correct,
            "human_total": len(human),
            "recall_percentage": _percentage(recall_correct, len(human)),
        }

    matrix = {
        human_label: {predicted_role: 0 for predicted_role in ROLE_ORDER}
        for human_label in ROLE_ORDER
    }
    correct = 0
    for row in evaluated:
        human_label = row["human_label"]
        predicted_role = row["predicted_role"]
        matrix[human_label][predicted_role] += 1
        correct += human_label == predicted_role
    return {
        "evaluated": len(evaluated),
        "correct": correct,
        "accuracy_percentage": _percentage(correct, len(evaluated)),
        "precision_by_role": precision_by_role,
        "recall_by_role": recall_by_role,
        "confusion_matrix": {
            "rows": list(ROLE_ORDER),
            "columns": list(ROLE_ORDER),
            "values": matrix,
        },
    }


def classification_metric_slices(
    rows: Iterable[Mapping[str, object]],
    prompt_development_domains: Iterable[str],
) -> dict[str, dict[str, object]]:
    evaluated = list(rows)
    excluded = {
        normalize_classifier_domain(domain)
        for domain in prompt_development_domains
    }
    return {
        "sample_1": classification_metrics(
            row for row in evaluated if 1 in row.get("samples", ())
        ),
        "sample_2": classification_metrics(
            row for row in evaluated if 2 in row.get("samples", ())
        ),
        "excluding_prompt_development": classification_metrics(
            row for row in evaluated if row.get("domain") not in excluded
        ),
        "all_unique": classification_metrics(evaluated),
    }
