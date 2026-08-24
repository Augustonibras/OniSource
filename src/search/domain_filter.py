from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_NOISE_DOMAINS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "noise_domains.yaml"
)
_LOCAL_SUFFIX_EXCLUSIONS = (".edu", ".edu.br", ".gov")


class NoiseDomainConfigError(ValueError):
    """Raised when the human-maintained noise-domain list is invalid."""


def _parse_quoted_domain(value: str, line_number: int) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise NoiseDomainConfigError(
            f"Noise domain at line {line_number} must be double quoted"
        ) from error
    if not isinstance(parsed, str):
        raise NoiseDomainConfigError(
            f"Noise domain at line {line_number} must be text"
        )
    domain = parsed.strip().casefold().rstrip(".")
    if not domain or "://" in domain or "/" in domain:
        raise NoiseDomainConfigError(f"Invalid noise domain at line {line_number}")
    return domain


def load_noise_domains(
    config_path: str | Path = DEFAULT_NOISE_DOMAINS_PATH,
) -> tuple[str, ...]:
    path = Path(config_path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise NoiseDomainConfigError(
            f"Could not read noise-domain configuration: {path}"
        ) from error

    domains: list[str] = []
    section_seen = False
    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith(" "):
            if stripped != "exclude_domains:":
                raise NoiseDomainConfigError(
                    f"Unexpected noise-domain YAML at line {line_number}"
                )
            section_seen = True
            continue
        if not section_seen or not raw_line.startswith("  - "):
            raise NoiseDomainConfigError(
                f"Invalid noise-domain YAML at line {line_number}"
            )
        domains.append(
            _parse_quoted_domain(raw_line[len("  - ") :].strip(), line_number)
        )

    if not section_seen or not domains:
        raise NoiseDomainConfigError("exclude_domains must contain at least one domain")
    return tuple(dict.fromkeys(domains))


class SearchDomainFilter:
    def __init__(
        self,
        noise_domains_path: str | Path = DEFAULT_NOISE_DOMAINS_PATH,
    ) -> None:
        self.exclude_domains = load_noise_domains(noise_domains_path)

    def excludes_url(self, url: str) -> bool:
        return self.match_reason(url) is not None

    def match_reason(self, url: str) -> str | None:
        hostname = urlsplit(url).hostname
        if hostname is None:
            return None
        domain = hostname.casefold().rstrip(".")
        for suffix in _LOCAL_SUFFIX_EXCLUSIONS:
            if domain.endswith(suffix):
                return f"LOCAL_SUFFIX:{suffix}"
        for excluded in self.exclude_domains:
            if domain == excluded or domain.endswith(f".{excluded}"):
                return f"EXCLUDE_DOMAIN:{excluded}"
        return None

    def filter_raw_results(self, raw_results: list[Any]) -> list[Any]:
        filtered: list[Any] = []
        for item in raw_results:
            if not isinstance(item, dict):
                filtered.append(item)
                continue
            url = item.get("url")
            if not isinstance(url, str) or not self.excludes_url(url):
                filtered.append(item)
        return filtered
