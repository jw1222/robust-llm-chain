"""Anthropic Direct adapter.

Implementation in Phase 4 (T6). Stub keeps the module importable so
``register_adapter`` calls and the public surface are stable.
"""

from collections.abc import Mapping
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel

from robust_llm_chain.types import ProviderSpec


class AnthropicAdapter:
    """``ChatAnthropic`` builder. Phase 4 (T6) implementation."""

    type: ClassVar[str] = "anthropic"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct ``ChatAnthropic`` from ``spec``. Phase 4 (T6)."""
        raise NotImplementedError("AnthropicAdapter.build is implemented in Phase 4 (T6).")

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Return ``{"api_key": ...}`` if ``ANTHROPIC_API_KEY`` set. Phase 4 (T6)."""
        raise NotImplementedError(
            "AnthropicAdapter.credentials_present is implemented in Phase 4 (T6)."
        )
