"""Unit tests for ``robust_llm_chain.errors``.

Phase 3 scope: hierarchy + ``AllProvidersFailed`` payload + a few
representative ``is_fallback_eligible`` cases. The full classifier matrix
lands in Phase 4 (T2 expansion).
"""

import pytest

from robust_llm_chain.errors import (
    AllProvidersFailed,
    BackendUnavailable,
    FallbackNotApplicable,
    ModelDeprecated,
    ModelNotFound,
    NoProvidersConfigured,
    ProviderInactive,
    ProviderModelCreationFailed,
    ProviderTimeout,
    RobustChainError,
    StreamInterrupted,
    is_fallback_eligible,
)
from robust_llm_chain.types import AttemptRecord

_ALL_ERROR_CLASSES = [
    NoProvidersConfigured,
    ProviderInactive,
    ProviderTimeout,
    ProviderModelCreationFailed,
    ModelDeprecated,
    ModelNotFound,
    FallbackNotApplicable,
    StreamInterrupted,
    BackendUnavailable,
    AllProvidersFailed,
]


# ──────────────────────────────────────────────────────────────────────────────
# Hierarchy
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("cls", _ALL_ERROR_CLASSES)
def test_all_errors_inherit_robust_chain_error(cls):
    assert issubclass(cls, RobustChainError)


def test_provider_timeout_carries_phase_and_elapsed():
    exc = ProviderTimeout(phase="first_token", elapsed_ms=15000.0)
    assert exc.phase == "first_token"
    assert exc.elapsed_ms == 15000.0
    assert "first_token" in str(exc)


def test_all_providers_failed_carries_attempts():
    a1 = AttemptRecord(
        provider_id="anthropic-direct",
        provider_type="anthropic",
        model_id="claude-haiku",
        phase="first_token",
        elapsed_ms=15000.0,
        error_type="OverloadedError",
        error_message="529",
        fallback_eligible=True,
        run_id=None,
    )
    a2 = AttemptRecord(
        provider_id="openrouter",
        provider_type="openrouter",
        model_id="anthropic/claude-haiku",
        phase="first_token",
        elapsed_ms=15000.0,
        error_type="RateLimitError",
        error_message="rate limit exceeded",
        fallback_eligible=True,
        run_id=None,
    )
    exc = AllProvidersFailed(attempts=[a1, a2])
    assert exc.attempts == [a1, a2]
    assert "anthropic-direct" in str(exc)
    assert "openrouter" in str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# is_fallback_eligible — three classification stages
# ──────────────────────────────────────────────────────────────────────────────


def test_typed_provider_timeout_is_eligible():
    assert is_fallback_eligible(ProviderTimeout(phase="first_token", elapsed_ms=15000.0))


def test_typed_fallback_not_applicable_is_not_eligible():
    assert is_fallback_eligible(FallbackNotApplicable("auth")) is False


def test_typed_model_deprecated_is_not_eligible():
    assert is_fallback_eligible(ModelDeprecated("sunset")) is False


def test_typed_model_not_found_is_not_eligible():
    assert is_fallback_eligible(ModelNotFound("unknown model")) is False


def test_typed_backend_unavailable_is_eligible():
    assert is_fallback_eligible(BackendUnavailable("memcached down"))


def test_keyword_overloaded_is_eligible():
    assert is_fallback_eligible(RuntimeError("provider returned 529 Overloaded"))


def test_keyword_rate_limit_is_eligible():
    assert is_fallback_eligible(RuntimeError("rate limit exceeded"))


def test_keyword_auth_is_not_eligible():
    assert is_fallback_eligible(RuntimeError("401 Unauthorized")) is False


def test_unknown_error_default_is_not_eligible():
    assert is_fallback_eligible(RuntimeError("unrelated message")) is False


# ──────────────────────────────────────────────────────────────────────────────
# context preservation
# ──────────────────────────────────────────────────────────────────────────────


def test_backend_unavailable_preserves_cause():
    original = OSError("connection refused")
    try:
        try:
            raise original
        except OSError as e:
            raise BackendUnavailable("memcached unreachable") from e
    except BackendUnavailable as exc:
        assert exc.__cause__ is original
