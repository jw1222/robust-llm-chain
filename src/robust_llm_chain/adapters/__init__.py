"""Provider adapters: built-in (``anthropic``, ``openrouter``) + extensible registry.

Public surface: ``ProviderAdapter`` Protocol, ``register_adapter``,
``get_adapter``. Custom adapters (e.g. Mistral) implement the Protocol and
register themselves; built-in adapters use the same interface — no special
treatment.
"""

from collections.abc import Mapping
from typing import ClassVar, Protocol

from langchain_core.language_models.chat_models import BaseChatModel

from robust_llm_chain.types import ProviderSpec


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


__all__ = ["ProviderAdapter", "get_adapter", "register_adapter"]
