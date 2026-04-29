"""Unit tests for ``robust_llm_chain.adapters.openai.OpenAIAdapter``.

Phase 4 (T6 후속) — Round 0 결정 변경 후 v0.1에 추가된 OpenAI 어댑터.
``langchain-openai`` 패키지를 OpenRouter 어댑터와 공유하되 ``base_url`` 을
설정하지 않음으로써 OpenAI 본 endpoint 로 라우팅.
"""

import sys

from langchain_openai import ChatOpenAI

from robust_llm_chain.adapters.openai import OpenAIAdapter
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ModelSpec, ProviderSpec


def _spec(*, max_output_tokens: int | None = None, api_key: str | None = "sk-test") -> ProviderSpec:
    return ProviderSpec(
        id="openai-direct",
        type="openai",
        model=ModelSpec(model_id="gpt-4o-mini", max_output_tokens=max_output_tokens),
        api_key=api_key,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Identity / shape
# ──────────────────────────────────────────────────────────────────────────────


def test_openai_adapter_type_constant():
    assert OpenAIAdapter.type == "openai"


# ──────────────────────────────────────────────────────────────────────────────
# build()
# ──────────────────────────────────────────────────────────────────────────────


def test_build_returns_chat_openai_with_openai_endpoint():
    chat = OpenAIAdapter().build(_spec())
    assert isinstance(chat, ChatOpenAI)
    # OpenAI endpoint — base_url unset (None) means default OpenAI URL.
    assert chat.openai_api_base is None or "openai.com" in str(chat.openai_api_base)


def test_build_passes_model_id_unchanged():
    chat = OpenAIAdapter().build(_spec())
    assert chat.model_name == "gpt-4o-mini"


def test_build_passes_max_output_tokens_when_provided():
    chat = OpenAIAdapter().build(_spec(max_output_tokens=512))
    assert chat.max_tokens == 512


def test_build_defaults_max_tokens_when_unset():
    chat = OpenAIAdapter().build(_spec(max_output_tokens=None))
    assert chat.max_tokens == 4096


def test_build_omits_api_key_when_spec_api_key_is_none(monkeypatch):
    """spec.api_key=None → ChatOpenAI picks up OPENAI_API_KEY from env."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env-1234567890")
    chat = OpenAIAdapter().build(_spec(api_key=None))
    assert chat.openai_api_key.get_secret_value() == "sk-from-env-1234567890"


def test_build_raises_provider_inactive_when_extras_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai", None)
    try:
        OpenAIAdapter().build(_spec())
    except ProviderInactive as e:
        assert "openai" in str(e).lower()
    else:
        raise AssertionError("expected ProviderInactive when extras missing")


# ──────────────────────────────────────────────────────────────────────────────
# credentials_present()
# ──────────────────────────────────────────────────────────────────────────────


def test_credentials_present_returns_api_key_when_env_set():
    creds = OpenAIAdapter().credentials_present({"OPENAI_API_KEY": "sk-openai"})
    assert creds == {"api_key": "sk-openai"}


def test_credentials_absent_returns_none():
    assert OpenAIAdapter().credentials_present({}) is None
    assert OpenAIAdapter().credentials_present({"OTHER_KEY": "x"}) is None


def test_credentials_independent_from_openrouter():
    """OPENAI_API_KEY must not satisfy OpenRouter (different env contract)."""
    # OpenRouter uses OPENROUTER_API_KEY; OpenAI here only sees OPENAI_API_KEY.
    assert OpenAIAdapter().credentials_present({"OPENROUTER_API_KEY": "x"}) is None
