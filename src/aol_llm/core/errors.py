"""Provider error taxonomy."""


class ProviderError(Exception):
    """Base for all provider-originating errors."""


class AuthError(ProviderError):
    """Missing or invalid API credentials."""


class RateLimitError(ProviderError):
    """Provider rejected the request due to rate limits."""


class ContextLengthError(ProviderError):
    """Request exceeded the provider context window."""


class ContentFilterError(ProviderError):
    """Provider refused the request on policy grounds."""


class NetworkError(ProviderError):
    """Provider request failed due to connection or timeout problems."""


class UnknownProviderError(ProviderError):
    """Provider request failed for an unclassified reason."""
