"""Unit tests for ``robust_llm_chain.types``.

Phase 3 scope: ``TokenUsage`` arithmetic + ``ProviderSpec`` masking + basic
dataclass shape. Phase 4 adds ``ChainResult`` lifecycle mutability and the
``RobustChainInput`` alias contract.
"""

from typing import get_args

from langchain_core.messages import AIMessage

from robust_llm_chain.types import (
    AttemptRecord,
    ChainResult,
    ModelSpec,
    PricingSpec,
    ProviderSpec,
    RobustChainInput,
    TimeoutConfig,
    TokenUsage,
)

# ──────────────────────────────────────────────────────────────────────────────
# TokenUsage arithmetic
# ──────────────────────────────────────────────────────────────────────────────


def test_token_usage_add_combines_fields():
    a = TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3)
    b = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
    c = a + b
    assert c.input_tokens == 11
    assert c.output_tokens == 22
    assert c.total_tokens == 33


def test_token_usage_iadd_mutates_in_place():
    a = TokenUsage(input_tokens=5, output_tokens=10, total_tokens=15)
    a += TokenUsage(input_tokens=2, output_tokens=4, total_tokens=6)
    assert a.input_tokens == 7
    assert a.output_tokens == 14
    assert a.total_tokens == 21


def test_token_usage_add_includes_cache_fields():
    a = TokenUsage(cache_read_tokens=100, cache_write_tokens=50)
    b = TokenUsage(cache_read_tokens=10, cache_write_tokens=5)
    c = a + b
    assert c.cache_read_tokens == 110
    assert c.cache_write_tokens == 55


# ──────────────────────────────────────────────────────────────────────────────
# ProviderSpec masking
# ──────────────────────────────────────────────────────────────────────────────


def test_provider_spec_repr_does_not_expose_api_key():
    spec = ProviderSpec(
        id="anthropic-direct",
        type="anthropic",
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
        api_key="sk-ant-api03-secret-value-do-not-leak-1234567890",
    )
    text = repr(spec)
    assert "sk-ant" not in text
    assert "secret-value" not in text
    assert "anthropic-direct" in text
    assert "claude-haiku-4-5-20251001" in text


def test_provider_spec_repr_does_not_expose_aws_secret():
    spec = ProviderSpec(
        id="bedrock-east",
        type="bedrock",
        model=ModelSpec(model_id="anthropic.claude-haiku"),
        aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
    )
    text = repr(spec)
    assert "AKIA" not in text
    assert "wJalr" not in text
    assert "us-east-1" in text


def test_provider_spec_slots_blocks_dict_access():
    """``slots=True`` removes ``__dict__`` so ``vars()`` cannot bypass repr."""
    spec = ProviderSpec(
        id="x",
        type="anthropic",
        model=ModelSpec(model_id="m"),
        api_key="sk-secret",
    )
    # Either AttributeError on ``__dict__`` or TypeError on ``vars()`` is
    # acceptable depending on Python's behavior for slot-only dataclasses.
    try:
        _ = spec.__dict__
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ProviderSpec should not expose __dict__ when slots=True")


def test_provider_spec_pickle_drops_credentials():
    """Pickle serialization must not include credential fields.

    Hardening: prevents credentials from leaking through ``pickle.dumps`` (e.g.
    distributed task queues, cache layers, multiprocess transports). The
    unpickled clone preserves all non-credential fields.
    """
    import pickle

    secret_marker = "do-not-leak-via-pickle-9876543210"
    aws_secret_marker = "AWS-pickle-leak-canary-zzzzzzzz"
    spec = ProviderSpec(
        id="anthropic-direct",
        type="anthropic",
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
        api_key=secret_marker,
        aws_access_key_id="AKIA-pickle-canary",
        aws_secret_access_key=aws_secret_marker,
        region="us-east-1",
        priority=5,
    )

    blob = pickle.dumps(spec)
    # Raw bytes must not contain credential strings.
    assert secret_marker.encode() not in blob
    assert aws_secret_marker.encode() not in blob
    assert b"AKIA-pickle-canary" not in blob

    restored = pickle.loads(blob)
    # Credentials cleared on restore.
    assert restored.api_key is None
    assert restored.aws_access_key_id is None
    assert restored.aws_secret_access_key is None
    # Non-credential fields preserved.
    assert restored.id == "anthropic-direct"
    assert restored.type == "anthropic"
    assert restored.model.model_id == "claude-haiku-4-5-20251001"
    assert restored.region == "us-east-1"
    assert restored.priority == 5


def test_provider_spec_compare_ignores_credentials():
    """Equality must ignore credential fields.

    Hardening: prevents credentials from leaking via pytest assertion
    introspection — when two specs compare equal on identity but differ on
    api_key, pytest would otherwise diff and print credential values in the
    failure output.
    """
    base_kwargs = {
        "id": "anthropic-direct",
        "type": "anthropic",
        "model": ModelSpec(model_id="claude-haiku-4-5-20251001"),
        "region": "us-east-1",
        "priority": 0,
    }
    a = ProviderSpec(**base_kwargs, api_key="sk-secret-A")
    b = ProviderSpec(**base_kwargs, api_key="sk-secret-B")
    c = ProviderSpec(
        **base_kwargs,
        aws_access_key_id="AKIA-different",
        aws_secret_access_key="aws-secret-different",
    )

    assert a == b, "credential difference must not affect equality"
    assert a == c, "credential difference must not affect equality"


# ──────────────────────────────────────────────────────────────────────────────
# Other dataclasses — basic shape
# ──────────────────────────────────────────────────────────────────────────────


def test_model_spec_pricing_optional():
    spec = ModelSpec(model_id="claude-haiku")
    assert spec.pricing is None
    assert spec.max_output_tokens is None


def test_pricing_spec_defaults_currency_usd():
    p = PricingSpec(input_per_1m=0.80, output_per_1m=4.00)
    assert p.currency == "USD"
    assert p.cache_read_per_1m is None
    assert p.cache_write_per_1m is None


def test_timeout_config_defaults():
    t = TimeoutConfig()
    assert t.per_provider == 60.0
    assert t.first_token == 15.0
    assert t.total is None
    assert t.stream_cleanup == 2.0


# ──────────────────────────────────────────────────────────────────────────────
# ChainResult — astream lifecycle requires mutability
# ──────────────────────────────────────────────────────────────────────────────


def test_chain_result_mutable_for_lifecycle():
    """Astream commits provisional result first then mutates fields per stage.

    The class must allow both ``attempts.append(...)`` and direct field
    reassignment (``output``, ``usage``, ``provider_used``) so the five-stage
    lifecycle in CONCEPT §8.0 / api-design §3.4 works.
    """
    spec = ProviderSpec(id="p1", type="fake", model=ModelSpec(model_id="m"))
    other_spec = ProviderSpec(id="p2", type="fake", model=ModelSpec(model_id="m2"))
    result = ChainResult(
        input=[],
        output=AIMessage(content=""),
        usage=TokenUsage(),
        cost=None,
        provider_used=spec,
        model_used=spec.model,
        attempts=[],
        elapsed_ms=0.0,
    )

    result.attempts.append(
        AttemptRecord(
            provider_id="p1",
            provider_type="fake",
            model_id="m",
            phase="first_token",
            elapsed_ms=10.0,
            error_type="OverloadedError",
            error_message="529",
            fallback_eligible=True,
            run_id=None,
        )
    )
    assert len(result.attempts) == 1

    # Final commit reassigns output / usage / provider_used.
    result.output = AIMessage(content="done")
    result.usage = TokenUsage(input_tokens=5, output_tokens=10, total_tokens=15)
    result.provider_used = other_spec
    result.model_used = other_spec.model
    result.elapsed_ms = 1234.0

    assert result.output.content == "done"
    assert result.usage.input_tokens == 5
    assert result.provider_used.id == "p2"
    assert result.elapsed_ms == 1234.0


# ──────────────────────────────────────────────────────────────────────────────
# RobustChainInput — public type alias contract
# ──────────────────────────────────────────────────────────────────────────────


def test_robust_chain_input_alias_includes_expected_members():
    """The alias must expose the three accepted Runnable input shapes.

    ``RobustChainInput`` is a ``TypeAlias`` annotation (PEP 613), so the
    runtime value is the ``str | PromptValue | list[BaseMessage]`` union
    object directly — ``get_args`` returns its three members.
    """
    members = get_args(RobustChainInput)
    member_reprs = {repr(m) for m in members}

    assert str in members
    assert any("PromptValue" in r for r in member_reprs)
    assert any("BaseMessage" in r and "list" in r for r in member_reprs)
