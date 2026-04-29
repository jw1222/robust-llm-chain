"""Anthropic Direct adapter — wraps ``langchain_anthropic.ChatAnthropic``.

Activated by ``pip install "robust-llm-chain[anthropic]"``. The library only
imports ``langchain_anthropic`` lazily inside ``build`` so the package stays
import-clean when the extras are not installed.
"""

from collections.abc import Mapping
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from robust_llm_chain.adapters import DEFAULT_MAX_OUTPUT_TOKENS, env_api_key_credentials
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ProviderSpec


class AnthropicAdapter:
    """Build ``ChatAnthropic`` instances from ``ProviderSpec``."""

    type: ClassVar[str] = "anthropic"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct ``ChatAnthropic`` from ``spec``.

        Raises:
            ProviderInactive: ``langchain_anthropic`` is not importable
                (extras missing or sentinel-stubbed by tests).
        """
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise ProviderInactive(
                'anthropic adapter requires `pip install "robust-llm-chain[anthropic]"`'
            ) from e

        # Pydantic mypy plugin sees only the field aliases (``model_name`` /
        # ``max_tokens_to_sample`` / ``api_key``). ``populate_by_name=True`` is
        # set on ChatAnthropic so callers may use either name at runtime, but
        # using the aliases keeps mypy --strict green.
        # When ``spec.api_key`` is ``None`` we omit the kwarg entirely so the
        # ChatAnthropic ``default_factory`` reads ``ANTHROPIC_API_KEY`` from env.
        max_tokens = spec.model.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        if spec.api_key is None:
            return ChatAnthropic(
                model_name=spec.model.model_id,
                max_tokens_to_sample=max_tokens,
                timeout=None,
                stop=None,
            )
        return ChatAnthropic(
            model_name=spec.model.model_id,
            max_tokens_to_sample=max_tokens,
            api_key=SecretStr(spec.api_key),
            timeout=None,
            stop=None,
        )

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Return ``{"api_key": ...}`` if ``ANTHROPIC_API_KEY`` is set, else ``None``."""
        return env_api_key_credentials(env, "ANTHROPIC_API_KEY")
