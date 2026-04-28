"""Unit tests for ``robust_llm_chain.adapters`` Protocol + registry.

Phase 4 (T5) coverage. The ``adapters/__init__.py`` module was implemented
in Phase 3; these tests pin its observable behaviour:

- Protocol shape (``type`` / ``build(spec)`` / ``credentials_present(env)``)
- ``register_adapter`` makes an adapter retrievable via ``get_adapter``
- ``get_adapter`` of an unknown ``type`` raises ``KeyError``
- Re-registering the same ``type`` overwrites the prior entry
- ``conftest._reset_adapter_registry`` autouse fixture isolates each test
"""

import inspect
from collections.abc import Mapping
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel

from robust_llm_chain.adapters import (
    _ADAPTER_REGISTRY,
    ProviderAdapter,
    get_adapter,
    register_adapter,
)
from robust_llm_chain.types import ProviderSpec

# ──────────────────────────────────────────────────────────────────────────────
# Test doubles — minimal Protocol-satisfying adapters
# ──────────────────────────────────────────────────────────────────────────────


class _DummyAdapter:
    """Adapter satisfying ``ProviderAdapter`` for registry tests only."""

    type: ClassVar[str] = "dummy"
    label: str = "v1"

    def build(self, spec: ProviderSpec) -> BaseChatModel:  # pragma: no cover - never invoked
        raise NotImplementedError

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        return {} if env else None


class _DummyAdapterV2(_DummyAdapter):
    """Same ``type`` as ``_DummyAdapter`` but distinguishable by ``label``."""

    label: str = "v2"


# ──────────────────────────────────────────────────────────────────────────────
# Protocol shape
# ──────────────────────────────────────────────────────────────────────────────


def test_protocol_defines_required_members():
    """Protocol must declare ``type`` ClassVar + ``build`` + ``credentials_present``."""
    methods = {m for m in dir(ProviderAdapter) if not m.startswith("_")}
    assert "build" in methods
    assert "credentials_present" in methods
    # ``type`` is declared via ``ClassVar`` annotation only (no class-body
    # default), so it shows up in ``__annotations__`` rather than ``dir``.
    assert "type" in ProviderAdapter.__annotations__


def test_protocol_build_signature_takes_spec():
    sig = inspect.signature(ProviderAdapter.build)
    assert "spec" in sig.parameters


def test_protocol_credentials_present_signature_takes_env():
    sig = inspect.signature(ProviderAdapter.credentials_present)
    assert "env" in sig.parameters


# ──────────────────────────────────────────────────────────────────────────────
# register_adapter / get_adapter
# ──────────────────────────────────────────────────────────────────────────────


def test_register_adapter_adds_to_registry():
    adapter = _DummyAdapter()
    register_adapter(adapter)
    assert get_adapter("dummy") is adapter


def test_get_adapter_unknown_type_raises_keyerror():
    try:
        get_adapter("mistral")
    except KeyError as e:
        assert "mistral" in str(e)
    else:
        raise AssertionError("expected KeyError for unregistered adapter type")


def test_register_overwrites_same_type():
    first = _DummyAdapter()
    second = _DummyAdapterV2()
    register_adapter(first)
    register_adapter(second)
    looked_up = get_adapter("dummy")
    assert looked_up is second
    assert getattr(looked_up, "label", None) == "v2"


# ──────────────────────────────────────────────────────────────────────────────
# Registry isolation — conftest autouse fixture
# ──────────────────────────────────────────────────────────────────────────────
#
# These two tests are deliberately ordered: if the autouse fixture were
# missing, ``test_registry_isolated_step_b_starts_clean`` would still observe
# the registration from step A and fail.


def test_registry_isolated_step_a_seeds_dummy():
    register_adapter(_DummyAdapter())
    assert "dummy" in _ADAPTER_REGISTRY


def test_registry_isolated_step_b_starts_clean():
    """conftest._reset_adapter_registry must wipe registrations from step A."""
    assert "dummy" not in _ADAPTER_REGISTRY
