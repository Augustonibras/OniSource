from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from src.simple_yaml import load_yaml_mapping


DEFAULT_MARKETPLACE_DOMAINS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "marketplace_domains.yaml"
)


class MarketplaceDomainConfigError(ValueError):
    """Raised when the human marketplace-domain list is invalid."""


def load_marketplace_domains(
    config_path: str | Path = DEFAULT_MARKETPLACE_DOMAINS_PATH,
) -> tuple[str, ...]:
    try:
        payload = load_yaml_mapping(config_path)
    except (OSError, ValueError) as error:
        raise MarketplaceDomainConfigError(
            f"Could not read marketplace-domain configuration: {config_path}"
        ) from error
    raw_domains = payload.get("marketplace_domains")
    if not isinstance(raw_domains, list) or not raw_domains:
        raise MarketplaceDomainConfigError(
            "marketplace_domains must contain at least one domain"
        )

    domains: list[str] = []
    for raw_domain in raw_domains:
        if not isinstance(raw_domain, str):
            raise MarketplaceDomainConfigError(
                "marketplace domain entries must be text"
            )
        domain = raw_domain.strip().casefold().rstrip(".")
        if not domain or "://" in domain or "/" in domain:
            raise MarketplaceDomainConfigError(
                f"Invalid marketplace domain: {raw_domain!r}"
            )
        domains.append(domain)
    return tuple(dict.fromkeys(domains))


class MarketplaceDomainRegistry:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_MARKETPLACE_DOMAINS_PATH,
    ) -> None:
        self.domains = load_marketplace_domains(config_path)

    def matches_domain(self, domain: str) -> bool:
        return self.matching_pattern(domain) is not None

    def matching_pattern(self, domain: str) -> str | None:
        normalized = domain.strip().casefold().rstrip(".")
        return next(
            (
                marketplace
                for marketplace in self.domains
                if normalized == marketplace
                or normalized.endswith(f".{marketplace}")
            ),
            None,
        )

    def matches_url(self, url: str) -> bool:
        hostname = urlsplit(url).hostname
        return hostname is not None and self.matches_domain(hostname)

    def match_reason(self, url: str) -> str | None:
        hostname = urlsplit(url).hostname
        if hostname is None:
            return None
        pattern = self.matching_pattern(hostname)
        return None if pattern is None else f"MARKETPLACE_DOMAIN:{pattern}"
