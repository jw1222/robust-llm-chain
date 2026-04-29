"""Unit tests for ``robust_llm_chain._security`` (internal helpers).

Covers the small but security-critical ``sanitize_message`` branches that
``test_observability.test_cleanup_run_sanitizes_credential_in_error_before_sending``
exercises end-to-end. These are direct unit tests for pattern coverage and
edge cases (None input, truncation, multi-pattern hit).
"""

from robust_llm_chain._security import sanitize_message


def test_sanitize_none_returns_none():
    """``None`` input passes through unchanged — supports optional error fields."""
    assert sanitize_message(None) is None


def test_sanitize_truncates_when_over_max_len():
    """Strings longer than ``max_len`` are truncated with ``"..."`` suffix.

    Uses chars outside the base64 alphabet (whitespace) so the catchall
    40-char base64 pattern does not collapse the input first.
    """
    long = " " * 250
    out = sanitize_message(long, max_len=200)
    assert out is not None
    assert len(out) == 203  # 200 + "..."
    assert out.endswith("...")


def test_sanitize_short_string_unchanged():
    """Strings within ``max_len`` are returned without truncation."""
    short = "no credentials here"
    assert sanitize_message(short) == short


def test_sanitize_masks_provider_api_key_prefix():
    """sk-... prefix (Anthropic / OpenAI / OpenRouter style) is masked."""
    out = sanitize_message("error: sk-ant-api03-canary-1234567890abcdef")
    assert out is not None
    assert "sk-ant" not in out
    assert "***" in out


def test_sanitize_masks_aws_access_key_id():
    """AKIA... prefix (AWS access key id) is masked."""
    out = sanitize_message("error: AKIAIOSFODNN7EXAMPLE leaked")
    assert out is not None
    assert "AKIA" not in out
    assert "***" in out


def test_sanitize_masks_langsmith_personal_token():
    """lsv2_pt_... prefix (LangSmith personal token) is masked."""
    out = sanitize_message("trace failed for lsv2_pt_canary_token_payload")
    assert out is not None
    assert "lsv2_pt" not in out
    assert "***" in out


def test_sanitize_truncation_applied_after_masking():
    """Masking happens before length cap — masked tokens still count toward max_len.

    Pad with whitespace (outside base64 alphabet) so only the explicit
    sk-... prefix is masked, then verify the result still gets truncated.
    """
    payload = " " * 220 + "sk-ant-api03-secret-1234567890abcd"
    out = sanitize_message(payload, max_len=200)
    assert out is not None
    assert "sk-ant" not in out  # sk-... prefix masked even when followed by truncation
    assert out.endswith("...")  # truncated
