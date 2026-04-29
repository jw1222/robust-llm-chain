"""Shared pytest fixtures and collection hooks.

- ``_reset_adapter_registry`` (autouse): snapshots the adapter registry
  before each test and restores it after. CONCEPT §15 — registry isolation
  for TDD.
- ``pytest_collection_modifyitems``: auto-skips integration / e2e tests
  whose required API key is not present (CODING_STYLE §10.6).
"""

import os

import pytest

from robust_llm_chain.adapters import _ADAPTER_REGISTRY


@pytest.fixture(autouse=True)
def _reset_adapter_registry() -> None:
    """Snapshot/restore the adapter registry around each test."""
    snapshot = dict(_ADAPTER_REGISTRY)
    yield
    _ADAPTER_REGISTRY.clear()
    _ADAPTER_REGISTRY.update(snapshot)


# ──────────────────────────────────────────────────────────────────────────────
# Auto-skip integration / e2e tests when keys are absent.
# ──────────────────────────────────────────────────────────────────────────────

_KEY_BY_MARKER: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",  # also requires AWS_SECRET_ACCESS_KEY / AWS_REGION
}


def pytest_collection_modifyitems(config, items):
    """Skip tests marked with provider markers when their keys are unset."""
    for item in items:
        for marker_name, env_var in _KEY_BY_MARKER.items():
            if marker_name in item.keywords and not os.environ.get(env_var):
                item.add_marker(pytest.mark.skip(reason=f"{env_var} not set"))
