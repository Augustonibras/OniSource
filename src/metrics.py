from __future__ import annotations

from dataclasses import dataclass

from src.models import UNKNOWN, PipelineMetrics


@dataclass(frozen=True, slots=True)
class PipelineRates:
    fetch_success_rate: float | str
    extraction_success_rate: float | str
    end_to_end_success_rate: float | str


def _safe_rate(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return UNKNOWN
    return numerator / denominator


def validate_metrics(metrics: PipelineMetrics) -> None:
    terminal_fetches = (
        metrics.fetch_success
        + metrics.fetch_blocked
        + metrics.fetch_timeout
        + metrics.fetch_form_required
        + metrics.fetch_js_required
    )
    if metrics.fetch_attempted != terminal_fetches:
        raise ValueError("fetch_attempted must equal the sum of terminal fetch states")
    if metrics.pdf_downloaded > metrics.pdf_candidates:
        raise ValueError("pdf_downloaded cannot exceed pdf_candidates")
    if metrics.pdf_parseable + metrics.pdf_scanned > metrics.pdf_downloaded:
        raise ValueError("parseable and scanned PDFs cannot exceed downloaded PDFs")
    if metrics.extraction_success > metrics.extraction_attempted:
        raise ValueError("extraction_success cannot exceed extraction_attempted")
    if metrics.verified_candidates > metrics.candidate_products:
        raise ValueError("verified_candidates cannot exceed candidate_products")


def calculate_rates(metrics: PipelineMetrics) -> PipelineRates:
    validate_metrics(metrics)
    return PipelineRates(
        fetch_success_rate=_safe_rate(metrics.fetch_success, metrics.fetch_attempted),
        extraction_success_rate=_safe_rate(
            metrics.extraction_success, metrics.extraction_attempted
        ),
        end_to_end_success_rate=_safe_rate(
            metrics.verified_candidates, metrics.candidate_products
        ),
    )
