"""Unit tests for ``RobustChainBuilder`` (fluent provider configuration).

The builder is the third path for configuring providers (alongside
``RobustChain.from_env`` and explicit ``RobustChain(providers=[...])``). It
collapses the dict/list semantic split — every pattern (single, multi-key,
multi-region, mixed) is the same chained method shape.

Builder API (v0.3.0+): ``add_provider(type=..., api_key=...)`` for single-key
providers + ``add_bedrock(...)`` for the asymmetric Bedrock case. Credentials
are passed as values; reading them from env / Secrets Manager is the caller's
job — the builder does not touch ``os.environ``.
"""

import pytest

from robust_llm_chain import RobustChain
from robust_llm_chain.backends import LocalBackend
from robust_llm_chain.errors import NoProvidersConfigured

# ──────────────────────────────────────────────────────────────────────────────
# Single-vendor and explicit api_key
# ──────────────────────────────────────────────────────────────────────────────


def test_builder_single_anthropic() -> None:
    chain = (
        RobustChain.builder()
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key="sk-ant-test-1234567890",
        )
        .build()
    )
    assert len(chain._providers) == 1
    assert chain._providers[0].type == "anthropic"
    assert chain._providers[0].api_key == "sk-ant-test-1234567890"
    assert chain._providers[0].model.model_id == "claude-haiku-4-5-20251001"


def test_builder_single_openai() -> None:
    chain = (
        RobustChain.builder()
        .add_provider(type="openai", model="gpt-4o-mini", api_key="sk-openai-test")
        .build()
    )
    assert chain._providers[0].type == "openai"
    assert chain._providers[0].api_key == "sk-openai-test"


def test_builder_single_openrouter() -> None:
    chain = (
        RobustChain.builder()
        .add_provider(
            type="openrouter",
            model="anthropic/claude-haiku-4.5",
            api_key="sk-or-test",
        )
        .build()
    )
    assert chain._providers[0].type == "openrouter"
    assert chain._providers[0].api_key == "sk-or-test"


# ──────────────────────────────────────────────────────────────────────────────
# Multi-key and multi-region
# ──────────────────────────────────────────────────────────────────────────────


def test_builder_multi_key_anthropic() -> None:
    """Two Anthropic keys — distinct values, distinct IDs, same type."""
    chain = (
        RobustChain.builder()
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key="sk-ant-primary-1",
            id="anthropic1",
        )
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key="sk-ant-backup-2",
            id="anthropic2",
        )
        .build()
    )
    assert len(chain._providers) == 2
    assert chain._providers[0].id == "anthropic1"
    assert chain._providers[0].api_key == "sk-ant-primary-1"
    assert chain._providers[1].id == "anthropic2"
    assert chain._providers[1].api_key == "sk-ant-backup-2"


def test_builder_bedrock_multi_region() -> None:
    """Bedrock east + west — same AWS keys, different region."""
    chain = (
        RobustChain.builder()
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-east-1",
            aws_access_key_id="AKIA-test",
            aws_secret_access_key="secret-test-do-not-leak",
            id="bedrock-east",
        )
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-west-2",
            aws_access_key_id="AKIA-test",
            aws_secret_access_key="secret-test-do-not-leak",
            id="bedrock-west",
        )
        .build()
    )
    assert len(chain._providers) == 2
    assert chain._providers[0].region == "us-east-1"
    assert chain._providers[1].region == "us-west-2"
    assert chain._providers[0].id == "bedrock-east"
    assert chain._providers[1].id == "bedrock-west"


def test_builder_bedrock_per_region_credentials() -> None:
    """Bedrock with distinct credentials per region (blast-radius isolation)."""
    chain = (
        RobustChain.builder()
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-east-1",
            aws_access_key_id="AKIA-east",
            aws_secret_access_key="secret-east",
        )
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-west-2",
            aws_access_key_id="AKIA-west",
            aws_secret_access_key="secret-west",
        )
        .build()
    )
    assert chain._providers[0].aws_access_key_id == "AKIA-east"
    assert chain._providers[1].aws_access_key_id == "AKIA-west"


# ──────────────────────────────────────────────────────────────────────────────
# Mixed vendors
# ──────────────────────────────────────────────────────────────────────────────


def test_builder_mixed_anthropic_openrouter() -> None:
    chain = (
        RobustChain.builder()
        .add_provider(type="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-ant-1")
        .add_provider(type="openrouter", model="anthropic/claude-haiku-4.5", api_key="sk-or-2")
        .build()
    )
    assert len(chain._providers) == 2
    assert chain._providers[0].type == "anthropic"
    assert chain._providers[1].type == "openrouter"


def test_builder_three_way_claude() -> None:
    """3-way Claude across Anthropic + Bedrock + OpenRouter — README pattern."""
    chain = (
        RobustChain.builder()
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key="sk-ant-1",
            priority=0,
        )
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-east-1",
            aws_access_key_id="AKIA-3",
            aws_secret_access_key="secret-3",
            priority=1,
        )
        .add_provider(
            type="openrouter",
            model="anthropic/claude-haiku-4.5",
            api_key="sk-or-2",
            priority=2,
        )
        .build()
    )
    assert len(chain._providers) == 3
    assert [p.type for p in chain._providers] == ["anthropic", "bedrock", "openrouter"]
    assert [p.priority for p in chain._providers] == [0, 1, 2]


# ──────────────────────────────────────────────────────────────────────────────
# Defaults and ergonomics
# ──────────────────────────────────────────────────────────────────────────────


def test_builder_default_id_auto_unique() -> None:
    """Two anthropic adds without explicit ``id`` get distinct auto-generated ids."""
    chain = (
        RobustChain.builder()
        .add_provider(type="anthropic", model="m", api_key="k1")
        .add_provider(type="anthropic", model="m", api_key="k2")
        .build()
    )
    ids = [p.id for p in chain._providers]
    assert len(set(ids)) == 2, f"ids must be unique, got {ids}"
    assert all(i.startswith("anthropic") for i in ids)


def test_builder_default_id_per_type() -> None:
    """Auto-id counter is per type — bedrock-1 + anthropic-1 coexist."""
    chain = (
        RobustChain.builder()
        .add_provider(type="anthropic", model="m", api_key="k1")
        .add_bedrock(
            model="m",
            region="us-east-1",
            aws_access_key_id="AKIA-x",
            aws_secret_access_key="sec-x",
        )
        .build()
    )
    ids = {p.id for p in chain._providers}
    assert ids == {"anthropic-1", "bedrock-1"}


def test_builder_priority_passthrough() -> None:
    chain = (
        RobustChain.builder()
        .add_provider(type="anthropic", model="m", api_key="sk-1", priority=0)
        .add_provider(type="openrouter", model="m", api_key="sk-2", priority=1)
        .build()
    )
    assert chain._providers[0].priority == 0
    assert chain._providers[1].priority == 1


def test_builder_build_passes_kwargs_to_chain() -> None:
    """``.build(backend=..., temperature=...)`` forwards to ``RobustChain.__init__``."""
    backend = LocalBackend()
    chain = (
        RobustChain.builder()
        .add_provider(type="anthropic", model="m", api_key="k1")
        .build(backend=backend, temperature=0.5)
    )
    assert chain._backend is backend
    assert chain._temperature == 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────────


def test_builder_empty_raises_no_providers() -> None:
    """``builder().build()`` with no providers added → ``NoProvidersConfigured``."""
    with pytest.raises(NoProvidersConfigured):
        RobustChain.builder().build()
