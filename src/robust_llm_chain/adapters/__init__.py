"""Provider adapters: extensible registry with four built-in adapters.

Built-in: ``anthropic``, ``openrouter``, ``openai``, ``bedrock``. Public
surface: ``ProviderAdapter`` Protocol, ``register_adapter``, ``get_adapter``.
Custom adapters (e.g. Mistral) implement the Protocol and register themselves;
built-in adapters use the same interface — no special treatment.
"""

from collections.abc import Mapping
from typing import ClassVar, Final, Protocol

from langchain_core.language_models.chat_models import BaseChatModel

from robust_llm_chain.types import ProviderSpec

#: Library default ``max_output_tokens`` shared across built-in adapters when
#: ``ModelSpec.max_output_tokens`` is unset. Centralized here so a single edit
#: shifts every adapter (CODING_STYLE §1.7 — 3-strike DRY).
DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 4096


class ProviderAdapter(Protocol):
    """Adapter Protocol: ``ProviderSpec`` → LangChain ``BaseChatModel``."""

    type: ClassVar[str]

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct a LangChain chat model from the given ``spec``.

        Raises:
            ProviderInactive: When the adapter's optional dependencies are
                not installed (extras missing).
            ProviderModelCreationFailed: When the SDK rejects the
                configuration.
        """
        ...

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Detect whether ``env`` carries this adapter's credentials.

        Returns the credential dict (e.g. ``{"api_key": "..."}``) when
        present, or ``None`` to indicate this provider is not enabled.
        """
        ...


# Module-level registry. ``conftest.py`` snapshots/restores this between tests
# (CONCEPT §15 — registry isolation).
_ADAPTER_REGISTRY: dict[str, ProviderAdapter] = {}


def register_adapter(adapter: ProviderAdapter) -> None:
    """Register ``adapter`` under its ``type`` (overwrites prior registration)."""
    _ADAPTER_REGISTRY[adapter.type] = adapter


def get_adapter(type_: str) -> ProviderAdapter:
    """Look up the adapter registered under ``type_``.

    Raises:
        KeyError: When no adapter of ``type_`` is registered.
    """
    return _ADAPTER_REGISTRY[type_]


def env_api_key_credentials(env: Mapping[str, str], env_var: str) -> dict[str, str] | None:
    """Detect a single ``api_key``-style credential from ``env``.

    Helper for adapters whose ``credentials_present`` is just "look up one env
    var, return ``{'api_key': ...}`` when set". Used by the three single-key
    built-in adapters (``anthropic``, ``openrouter``, ``openai``) — Bedrock has
    its own multi-field detector. Custom adapters with the same shape may use
    this directly (CODING_STYLE §1.7 — 3-strike DRY).
    """
    api_key = env.get(env_var)
    if api_key is None:
        return None
    return {"api_key": api_key}


__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "ProviderAdapter",
    "env_api_key_credentials",
    "get_adapter",
    "register_adapter",
]
