"""OpenAI Direct adapter — wraps ``langchain_openai.ChatOpenAI``.

Activated by ``pip install "robust-llm-chain[openai]"``. Reuses the same
``langchain-openai`` package as the OpenRouter adapter but leaves
``base_url`` unset so the client points at OpenAI's own endpoint.
"""

from collections.abc import Mapping
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from robust_llm_chain.adapters import DEFAULT_MAX_OUTPUT_TOKENS, env_api_key_credentials
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ProviderSpec


class OpenAIAdapter:
    """Build ``ChatOpenAI`` instances pointed at OpenAI's own endpoint."""

    type: ClassVar[str] = "openai"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct ``ChatOpenAI`` from ``spec``.

        Raises:
            ProviderInactive: ``langchain_openai`` is not importable.
        """
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ProviderInactive(
                'openai adapter requires `pip install "robust-llm-chain[openai]"`'
            ) from e

        max_tokens = spec.model.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        if spec.api_key is None:
            # Let ChatOpenAI pick up OPENAI_API_KEY from env via its own
            # default_factory — omit the kwarg entirely.
            return ChatOpenAI(model=spec.model.model_id, max_completion_tokens=max_tokens)
        return ChatOpenAI(
            model=spec.model.model_id,
            max_completion_tokens=max_tokens,
            api_key=SecretStr(spec.api_key),
        )

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Return ``{"api_key": ...}`` if ``OPENAI_API_KEY`` is set, else ``None``."""
        return env_api_key_credentials(env, "OPENAI_API_KEY")
