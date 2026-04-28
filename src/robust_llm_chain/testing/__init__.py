"""Testing utilities — explicitly imported by users / tests.

Importing this module does NOT register ``FakeAdapter`` automatically.
Users must call ``install_fake_adapter()`` (CONCEPT §15 — TDD isolation).
"""

from robust_llm_chain.testing.fake_adapter import (
    FakeAdapter,
    ProviderOverloaded,
    install_fake_adapter,
)

__all__ = ["FakeAdapter", "ProviderOverloaded", "install_fake_adapter"]
