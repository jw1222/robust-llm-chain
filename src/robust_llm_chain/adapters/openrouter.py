"""OpenRouter adapter — wraps ``langchain_openai.ChatOpenAI`` at OpenRouter's endpoint.

OpenRouter is OpenAI-compatible, so the OpenAI client suffices once
``base_url`` is pinned. Activated by
``pip install "robust-llm-chain[openrouter]"``.
"""

from collections.abc import Mapping
from typing import ClassVar, Final

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from robust_llm_chain.adapters import DEFAULT_MAX_OUTPUT_TOKENS, env_api_key_credentials
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ProviderSpec

#: OpenRouter's OpenAI-compatible endpoint.
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"


class OpenRouterAdapter:
    """Build ``ChatOpenAI`` instances pointed at OpenRouter from ``ProviderSpec``."""

    type: ClassVar[str] = "openrouter"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct ``ChatOpenAI(base_url=OPENROUTER_BASE_URL)`` from ``spec``.

        Raises:
            ProviderInactive: ``langchain_openai`` is not importable.
        """
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ProviderInactive(
                'openrouter adapter requires `pip install "robust-llm-chain[openrouter]"`'
            ) from e

        # Pydantic mypy plugin sees field aliases (``model`` / ``api_key`` /
        # ``base_url`` / ``max_completion_tokens``); ``populate_by_name=True``
        # is set on ChatOpenAI so callers may use either name at runtime.
        api_key = SecretStr(spec.api_key) if spec.api_key is not None else SecretStr("")
        return ChatOpenAI(
            model=spec.model.model_id,
            max_completion_tokens=spec.model.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Return ``{"api_key": ...}`` if ``OPENROUTER_API_KEY`` is set, else ``None``."""
        return env_api_key_credentials(env, "OPENROUTER_API_KEY")
