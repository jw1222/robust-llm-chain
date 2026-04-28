"""OpenRouter adapter (uses OpenAI-compatible SDK).

Implementation in Phase 4 (T7). Stub keeps the module importable.
"""

from collections.abc import Mapping
from typing import ClassVar, Final

from langchain_core.language_models.chat_models import BaseChatModel

from robust_llm_chain.types import ProviderSpec

#: OpenRouter's OpenAI-compatible endpoint.
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"


class OpenRouterAdapter:
    """``ChatOpenAI(base_url=OPENROUTER)`` builder. Phase 4 (T7)."""

    type: ClassVar[str] = "openrouter"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct OpenAI client pointed at OpenRouter. Phase 4 (T7)."""
        raise NotImplementedError("OpenRouterAdapter.build is implemented in Phase 4 (T7).")

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Return ``{"api_key": ...}`` if ``OPENROUTER_API_KEY`` set. Phase 4 (T7)."""
        raise NotImplementedError(
            "OpenRouterAdapter.credentials_present is implemented in Phase 4 (T7)."
        )
