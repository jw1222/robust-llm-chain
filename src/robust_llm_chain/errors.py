"""Exception hierarchy and ``is_fallback_eligible`` classifier.

CONCEPT.md §14 / api-design.md §6 reference. All exceptions inherit
``RobustChainError`` so callers can catch the family with one type.
"""

from typing import Literal

from robust_llm_chain.types import AttemptRecord


class RobustChainError(Exception):
    """Base class for all library-raised exceptions."""


class NoProvidersConfigured(RobustChainError):
    """Raised when zero providers are active (from_env returned empty)."""


class ProviderInactive(RobustChainError):
    """Adapter is installed but inactive in this version (placeholder extras)."""


class ProviderTimeout(RobustChainError):
    """Library-imposed timeout exceeded. ``phase`` indicates where."""

    def __init__(
        self,
        phase: Literal["first_token", "stream", "total", "model_creation"],
        elapsed_ms: float,
    ) -> None:
        self.phase = phase
        self.elapsed_ms = elapsed_ms
        super().__init__(f"provider timeout in phase={phase}, elapsed_ms={elapsed_ms:.1f}")


class ProviderModelCreationFailed(RobustChainError):
    """Adapter failed to construct ``BaseChatModel`` from ``ProviderSpec``."""


class ModelDeprecated(RobustChainError):
    """Provider response indicates the model is deprecated/sunset."""


class ModelNotFound(RobustChainError):
    """Provider response indicates the model id is unknown / 404."""


class FallbackNotApplicable(RobustChainError):
    """Authentication / parser / non-recoverable error — do not fallback."""


class StreamInterrupted(RobustChainError):
    """Streaming error after the first chunk was yielded (post-commit)."""


class BackendUnavailable(RobustChainError):
    """``IndexBackend`` is unreachable. fail-closed; no auto-fallback."""


class AllProvidersFailed(RobustChainError):
    """All configured providers exhausted. ``attempts`` lists every attempt."""

    def __init__(self, attempts: list[AttemptRecord]) -> None:
        self.attempts = attempts
        provider_ids = ", ".join(a.provider_id for a in attempts)
        super().__init__(f"all {len(attempts)} provider(s) failed: [{provider_ids}]")


# ──────────────────────────────────────────────────────────────────────────────
# Fallback classifier
# ──────────────────────────────────────────────────────────────────────────────

# Substrings that signal recoverable / retryable errors when typed exception
# and SDK-class checks didn't match.
_FALLBACK_KEYWORDS: tuple[str, ...] = (
    "529",
    "overloaded",
    "rate_limit",
    "rate limit",
    "throttling",
    "throttle",
    "timeout",
    "connection",
    "network",
    "502",
    "503",
    "504",
)

# Substrings that signal definitely non-recoverable errors.
_FALLBACK_NOT_APPLICABLE_KEYWORDS: tuple[str, ...] = (
    "401",
    "403",
    "auth",
    "api key",
    "invalid",
    "not found",
)

# Provider SDK exception class names (matched by ``type(exc).__name__`` to avoid
# importing optional SDKs).
_SDK_FALLBACK_CLASSES: frozenset[str] = frozenset(
    {
        "RateLimitError",
        "APITimeoutError",
        "OverloadedError",
        "ServiceUnavailableError",
        "InternalServerError",
        "APIConnectionError",
    }
)
_SDK_NOT_APPLICABLE_CLASSES: frozenset[str] = frozenset(
    {
        "AuthenticationError",
        "PermissionDeniedError",
        "OutputParserException",
        "ValidationError",
    }
)


def is_fallback_eligible(exc: BaseException) -> bool:
    """Classify whether ``exc`` warrants trying the next provider.

    Three-stage classification (CONCEPT.md §14):
        1. Typed library exceptions take precedence.
        2. Provider SDK exception class names matched by name (no import).
        3. Substring keyword fallback over ``str(exc)``.

    Args:
        exc: The exception raised by a provider call or library layer.

    Returns:
        ``True`` if the orchestrator should record an ``AttemptRecord`` and
        try the next provider; ``False`` if the error must propagate.
    """
    # Stage 1: typed library exceptions.
    if isinstance(exc, FallbackNotApplicable | ModelDeprecated | ModelNotFound):
        return False
    if isinstance(exc, ProviderTimeout | BackendUnavailable):
        return True

    # Stage 2: SDK class name matching (no import).
    cls_name = type(exc).__name__
    if cls_name in _SDK_FALLBACK_CLASSES:
        return True
    if cls_name in _SDK_NOT_APPLICABLE_CLASSES:
        return False

    # Stage 3: substring keyword fallback.
    msg = str(exc).lower()
    if any(k in msg for k in _FALLBACK_NOT_APPLICABLE_KEYWORDS):
        return False
    return any(k in msg for k in _FALLBACK_KEYWORDS)
