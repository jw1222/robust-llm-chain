"""Unit tests for ``robust_llm_chain.adapters.anthropic.AnthropicAdapter``.

Phase 4 (T6) RED → GREEN. Network calls are not made; we only verify that
``build`` constructs a ``ChatAnthropic`` with the expected arguments and that
``credentials_present`` mirrors the env contract.
"""

import sys

from langchain_anthropic import ChatAnthropic

from robust_llm_chain.adapters.anthropic import AnthropicAdapter
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ModelSpec, ProviderSpec


def _spec(*, max_output_tokens: int | None = None, api_key: str = "sk-ant-dummy") -> ProviderSpec:
    return ProviderSpec(
        id="anthropic-direct",
        type="anthropic",
        model=ModelSpec(
            model_id="claude-haiku-4-5-20251001",
            max_output_tokens=max_output_tokens,
        ),
        api_key=api_key,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Identity / shape
# ──────────────────────────────────────────────────────────────────────────────


def test_anthropic_adapter_type_constant():
    assert AnthropicAdapter.type == "anthropic"


# ──────────────────────────────────────────────────────────────────────────────
# build()
# ──────────────────────────────────────────────────────────────────────────────


def test_build_returns_chat_anthropic_with_model_id():
    chat = AnthropicAdapter().build(_spec())
    assert isinstance(chat, ChatAnthropic)
    assert chat.model == "claude-haiku-4-5-20251001"


def test_build_passes_max_output_tokens_when_provided():
    chat = AnthropicAdapter().build(_spec(max_output_tokens=2048))
    assert chat.max_tokens == 2048


def test_build_defaults_max_tokens_when_unset():
    """``ModelSpec.max_output_tokens=None`` falls back to the library default 4096."""
    chat = AnthropicAdapter().build(_spec(max_output_tokens=None))
    assert chat.max_tokens == 4096


def test_build_raises_provider_inactive_when_extras_missing(monkeypatch):
    """Simulate ``langchain_anthropic`` not being installed."""
    monkeypatch.setitem(sys.modules, "langchain_anthropic", None)
    try:
        AnthropicAdapter().build(_spec())
    except ProviderInactive as e:
        assert "anthropic" in str(e).lower()
    else:
        raise AssertionError("expected ProviderInactive when extras missing")


def test_build_falls_back_to_env_api_key_when_spec_api_key_is_none(monkeypatch):
    """spec.api_key=None: ChatAnthropic must read ``ANTHROPIC_API_KEY`` via
    its own ``default_factory``. Adapter must omit the kwarg rather than
    pass an empty SecretStr (which would override the factory)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env-1234567890")
    spec = ProviderSpec(
        id="anthropic-direct",
        type="anthropic",
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
        api_key=None,
    )
    chat = AnthropicAdapter().build(spec)
    assert chat.anthropic_api_key.get_secret_value() == "sk-ant-from-env-1234567890"


# ──────────────────────────────────────────────────────────────────────────────
# credentials_present()
# ──────────────────────────────────────────────────────────────────────────────


def test_credentials_present_returns_api_key_when_env_set():
    creds = AnthropicAdapter().credentials_present({"ANTHROPIC_API_KEY": "sk-ant-test"})
    assert creds == {"api_key": "sk-ant-test"}


def test_credentials_absent_returns_none():
    assert AnthropicAdapter().credentials_present({}) is None
    assert AnthropicAdapter().credentials_present({"OTHER_KEY": "x"}) is None
