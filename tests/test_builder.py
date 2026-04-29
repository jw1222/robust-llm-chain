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


@pytest.mark.parametrize(
    "provider_type,model,key",
    [
        ("anthropic", "claude-haiku-4-5-20251001", "sk-ant-test"),
        ("openai", "gpt-4o-mini", "sk-openai-test"),
        ("openrouter", "anthropic/claude-haiku-4.5", "sk-or-test"),
    ],
)
def test_builder_single_provider(provider_type: str, model: str, key: str) -> None:
    chain = (
        RobustChain.builder()
        .add_provider(type=provider_type, model=model, api_key=key)  # type: ignore[arg-type]
        .build()
    )
    spec = chain._providers[0]
    assert spec.type == provider_type
    assert spec.api_key == key
    assert spec.model.model_id == model


def test_builder_unknown_type_raises_at_build_time() -> None:
    """``add_provider(type="bogus", ...)`` fails fast with a clear ValueError."""
    with pytest.raises(ValueError) as excinfo:
        RobustChain.builder().add_provider(
            type="bogus",  # type: ignore[arg-type]
            model="m",
            api_key="k",
        )
    msg = str(excinfo.value)
    assert "bogus" in msg
    assert "anthropic" in msg  # listed in the expected-set


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


@pytest.mark.parametrize(
    "ak_east,sk_east,ak_west,sk_west",
    [
        # Typical: one IAM user covers all regions (AWS credentials are region-agnostic).
        ("AKIA-shared", "secret-shared", "AKIA-shared", "secret-shared"),
        # Blast-radius isolation: distinct IAM users per region.
        ("AKIA-east", "secret-east", "AKIA-west", "secret-west"),
    ],
    ids=["shared_credentials", "per_region_credentials"],
)
def test_builder_bedrock_multi_region(
    ak_east: str, sk_east: str, ak_west: str, sk_west: str
) -> None:
    """Bedrock east + west — covers both shared-creds (typical) and per-region cases."""
    chain = (
        RobustChain.builder()
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-east-1",
            aws_access_key_id=ak_east,
            aws_secret_access_key=sk_east,
            id="bedrock-east",
        )
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-west-2",
            aws_access_key_id=ak_west,
            aws_secret_access_key=sk_west,
            id="bedrock-west",
        )
        .build()
    )
    assert len(chain._providers) == 2
    assert chain._providers[0].id == "bedrock-east"
    assert chain._providers[0].region == "us-east-1"
    assert chain._providers[0].aws_access_key_id == ak_east
    assert chain._providers[1].id == "bedrock-west"
    assert chain._providers[1].region == "us-west-2"
    assert chain._providers[1].aws_access_key_id == ak_west


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


def test_builder_default_id_unique_across_mixed_types() -> None:
    """Auto-id guarantees uniqueness — exact format is implementation detail."""
    chain = (
        RobustChain.builder()
        .add_provider(type="anthropic", model="m", api_key="k1")
        .add_provider(type="anthropic", model="m", api_key="k2")
        .add_bedrock(
            model="m",
            region="us-east-1",
            aws_access_key_id="AKIA-x",
            aws_secret_access_key="sec-x",
        )
        .build()
    )
    ids = [p.id for p in chain._providers]
    assert len(set(ids)) == len(ids), f"ids must be unique, got {ids}"


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


def test_builder_empty_raises_no_providers() -> None:
    """``builder().build()`` with no providers added → ``NoProvidersConfigured``."""
    with pytest.raises(NoProvidersConfigured):
        RobustChain.builder().build()
