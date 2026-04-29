"""Public API surface contract — ARCHITECTURE §6.1/§6.2.

Anything imported via the documented surfaces (root re-exports +
subpaths) is part of the versioned public contract; breaking these
imports is a major-bumping change. These tests pin them so reorganizing
internals cannot accidentally drop a public symbol.
"""

import importlib

import robust_llm_chain

# ──────────────────────────────────────────────────────────────────────────────
# Root re-exports — ARCHITECTURE §6.1
# ──────────────────────────────────────────────────────────────────────────────

_EXPECTED_ROOT_EXPORTS = {
    "RobustChain",
    "RobustChainBuilder",
    "RobustChainInput",
    "SingleKeyProviderType",
    "ProviderSpec",
    "ModelSpec",
    "PricingSpec",
    "TokenUsage",
    "CostEstimate",
    "ChainResult",
    "AttemptRecord",
    "TimeoutConfig",
    "__version__",
}


def test_root_all_matches_architecture_6_1_table():
    assert set(robust_llm_chain.__all__) == _EXPECTED_ROOT_EXPORTS


def test_each_listed_symbol_is_actually_attribute():
    for name in robust_llm_chain.__all__:
        assert hasattr(robust_llm_chain, name), f"missing public symbol: {name}"


def test_version_string_is_set():
    assert isinstance(robust_llm_chain.__version__, str)
    assert robust_llm_chain.__version__  # non-empty


def test_robust_chain_importable_from_root():
    from robust_llm_chain import RobustChain

    assert RobustChain.__name__ == "RobustChain"


def test_robust_chain_input_alias_importable_from_root():
    from robust_llm_chain import RobustChainInput

    # PEP 695 type alias has __value__ attribute.
    assert hasattr(RobustChainInput, "__value__")


def test_builder_symbols_importable_from_root():
    """``RobustChainBuilder`` + ``SingleKeyProviderType`` are root-level public API."""
    from robust_llm_chain import RobustChain, RobustChainBuilder, SingleKeyProviderType

    # Builder is the recommended configuration path; classmethod on RobustChain
    # returns an instance.
    assert isinstance(RobustChain.builder(), RobustChainBuilder)
    # Literal alias narrows the ``add_provider(type=...)`` argument.
    from typing import get_args

    assert set(get_args(SingleKeyProviderType)) == {"anthropic", "openai", "openrouter"}


def test_dataclasses_importable_from_root():
    from robust_llm_chain import (
        AttemptRecord,
        ChainResult,
        CostEstimate,
        ModelSpec,
        PricingSpec,
        ProviderSpec,
        TimeoutConfig,
        TokenUsage,
    )

    # Sanity: dataclass instances can be constructed (those without required args).
    TokenUsage()
    TimeoutConfig()
    # The rest only check that import succeeds.
    assert ChainResult is not None
    assert CostEstimate is not None
    assert ModelSpec is not None
    assert PricingSpec is not None
    assert ProviderSpec is not None
    assert AttemptRecord is not None


# ──────────────────────────────────────────────────────────────────────────────
# Subpaths — ARCHITECTURE §6.2
# ──────────────────────────────────────────────────────────────────────────────


def test_errors_subpath_exposes_full_hierarchy():
    errors = importlib.import_module("robust_llm_chain.errors")
    expected = {
        "RobustChainError",
        "NoProvidersConfigured",
        "ProviderInactive",
        "ProviderTimeout",
        "ProviderModelCreationFailed",
        "ModelDeprecated",
        "ModelNotFound",
        "FallbackNotApplicable",
        "StreamInterrupted",
        "BackendUnavailable",
        "AllProvidersFailed",
        "is_fallback_eligible",
    }
    for name in expected:
        assert hasattr(errors, name), f"missing errors symbol: {name}"


def test_backends_subpath_exposes_protocol_and_implementations():
    backends = importlib.import_module("robust_llm_chain.backends")
    for name in ("IndexBackend", "LocalBackend", "MemcachedBackend", "MemcacheClient"):
        assert hasattr(backends, name), f"missing backends symbol: {name}"


def test_adapters_subpath_exposes_protocol_and_registry():
    adapters = importlib.import_module("robust_llm_chain.adapters")
    for name in ("ProviderAdapter", "register_adapter", "get_adapter"):
        assert hasattr(adapters, name), f"missing adapters symbol: {name}"


def test_testing_subpath_exposes_fake_adapter_and_installer():
    testing = importlib.import_module("robust_llm_chain.testing")
    for name in ("FakeAdapter", "install_fake_adapter", "ProviderOverloaded"):
        assert hasattr(testing, name), f"missing testing symbol: {name}"


# ──────────────────────────────────────────────────────────────────────────────
# Star-import safety — ``from robust_llm_chain import *`` should be deterministic
# ──────────────────────────────────────────────────────────────────────────────


def test_star_import_only_exposes_documented_symbols():
    namespace: dict[str, object] = {}
    exec("from robust_llm_chain import *", namespace)
    # Strip dunders that exec adds.
    public = {k for k in namespace if not k.startswith("_")} | {
        k for k in namespace if k == "__version__"
    }
    # Drop builtins exec injects.
    public.discard("__builtins__")
    assert public == _EXPECTED_ROOT_EXPORTS
