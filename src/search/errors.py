from __future__ import annotations


class SearchProviderError(RuntimeError):
    """Base class for explicit search-provider failures."""


class AuthError(SearchProviderError):
    """Authentication is absent or rejected with HTTP 401."""


class RateLimitError(SearchProviderError):
    """The provider returned HTTP 429 after the allowed attempts."""


class CreditsExhaustedError(SearchProviderError):
    """The provider reports that the account has no search credits."""


class SearchTimeoutError(SearchProviderError):
    """The provider did not respond within the configured timeout."""


class MalformedResponseError(SearchProviderError):
    """The provider response cannot be normalized safely."""


class SearchTransportError(SearchProviderError):
    """A non-timeout transport failure prevented the request."""


class UnexpectedHTTPStatusError(SearchProviderError):
    """The provider returned an unmapped HTTP failure status."""
