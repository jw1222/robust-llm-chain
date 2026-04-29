"""Internal security helpers for credential masking and message sanitization.

Used by ``ProviderSpec.__repr__`` and ``AttemptRecord.error_message`` to
prevent accidental key exposure in logs / repr / exception messages.

Not part of the public API.
"""

from __future__ import annotations

import re
from typing import Final

# Best-effort patterns — see SECURITY.md §2 for limitations (LangSmith service
# tokens, AWS STS / temporary credentials are NOT covered; the 40-char base64
# fallback can mask non-credential strings as a conservative trade-off).
_KEY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),  # Anthropic, OpenAI, OpenRouter
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"lsv2_pt_[A-Za-z0-9]+"),  # LangSmith personal token
    re.compile(r"[A-Za-z0-9/+=]{40}"),  # AWS secret (40-char base64) — conservative
)


def sanitize_message(text: str | None, max_len: int = 200) -> str | None:
    """Mask known key patterns and truncate to ``max_len``.

    Args:
        text: The string to sanitize. ``None`` is returned as ``None``.
        max_len: Maximum length before truncation; ``"..."`` is appended.

    Returns:
        Sanitized text, or ``None`` if input was ``None``.
    """
    if text is None:
        return None
    for pat in _KEY_PATTERNS:
        text = pat.sub("***", text)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text
