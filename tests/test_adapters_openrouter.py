"""Unit tests for ``robust_llm_chain.adapters.openrouter.OpenRouterAdapter``.

Phase 4 (T7) RED → GREEN. OpenRouter is OpenAI-compatible, so the adapter
wraps ``langchain_openai.ChatOpenAI`` with ``base_url`` pinned to OpenRouter.
"""

import sys

from langchain_openai import ChatOpenAI

from robust_llm_chain.adapters.openrouter import OPENROUTER_BASE_URL, OpenRouterAdapter
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ModelSpec, ProviderSpec


def _spec(
    *,
    model_id: str = "anthropic/claude-haiku-4.5",
    api_key: str = "sk-or-dummy",
    max_output_tokens: int | None = None,
) -> ProviderSpec:
    return ProviderSpec(
        id="openrouter",
        type="openrouter",
        model=ModelSpec(model_id=model_id, max_output_tokens=max_output_tokens),
        api_key=api_key,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Identity / shape
# ──────────────────────────────────────────────────────────────────────────────


def test_openrouter_adapter_type_constant():
    assert OpenRouterAdapter.type == "openrouter"


# ──────────────────────────────────────────────────────────────────────────────
# build()
# ──────────────────────────────────────────────────────────────────────────────


def test_build_returns_chat_openai_with_openrouter_base_url():
    chat = OpenRouterAdapter().build(_spec())
    assert isinstance(chat, ChatOpenAI)
    # ``openai_api_base`` is the field name; ``base_url`` is the alias.
    assert chat.openai_api_base == OPENROUTER_BASE_URL


def test_build_passes_model_id_unchanged():
    """Library does not rewrite OpenRouter model identifiers."""
    chat = OpenRouterAdapter().build(_spec(model_id="anthropic/claude-haiku-4.5"))
    assert chat.model_name == "anthropic/claude-haiku-4.5"


def test_build_passes_max_output_tokens_when_provided():
    chat = OpenRouterAdapter().build(_spec(max_output_tokens=1024))
    assert chat.max_tokens == 1024


def test_build_defaults_max_tokens_when_unset():
    chat = OpenRouterAdapter().build(_spec(max_output_tokens=None))
    assert chat.max_tokens == 4096


def test_build_raises_provider_inactive_when_extras_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai", None)
    try:
        OpenRouterAdapter().build(_spec())
    except ProviderInactive as e:
        assert "openrouter" in str(e).lower()
    else:
        raise AssertionError("expected ProviderInactive when extras missing")


# ──────────────────────────────────────────────────────────────────────────────
# credentials_present()
# ──────────────────────────────────────────────────────────────────────────────


def test_credentials_present_returns_api_key_when_env_set():
    creds = OpenRouterAdapter().credentials_present({"OPENROUTER_API_KEY": "sk-or-test"})
    assert creds == {"api_key": "sk-or-test"}


def test_credentials_absent_returns_none():
    assert OpenRouterAdapter().credentials_present({}) is None
    assert OpenRouterAdapter().credentials_present({"OPENAI_API_KEY": "x"}) is None
