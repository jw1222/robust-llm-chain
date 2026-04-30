"""Unit tests for ``robust_llm_chain.chain.RobustChain``.

Phase 4 (T10) — orchestrator + Hybrid API. ``FakeAdapter`` powers every
scenario so no real provider SDK call is made.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate

from robust_llm_chain.chain import RobustChain
from robust_llm_chain.errors import (
    AllProvidersFailed,
    NoProvidersConfigured,
    ProviderInactive,
    ProviderModelCreationFailed,
    ProviderTimeout,
    StreamInterrupted,
)
from robust_llm_chain.testing import FakeAdapter, ProviderOverloaded, install_fake_adapter
from robust_llm_chain.types import (
    ChainResult,
    ModelSpec,
    PricingSpec,
    ProviderSpec,
    TimeoutConfig,
)


def _fake_spec(provider_id: str, *, pricing: PricingSpec | None = None) -> ProviderSpec:
    return ProviderSpec(
        id=provider_id,
        type="fake",
        model=ModelSpec(model_id=f"m-{provider_id}", pricing=pricing),
    )


def _setup() -> FakeAdapter:
    return install_fake_adapter()


# ──────────────────────────────────────────────────────────────────────────────
# acall — happy path / fallback / all-fail / total timeout
# ──────────────────────────────────────────────────────────────────────────────


def test_acall_single_provider_success_returns_chain_result():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="hello")
        chain = RobustChain(providers=[_fake_spec("p1")])

        result = await chain.acall("hi")

        assert isinstance(result, ChainResult)
        assert result.output.content == "hello"
        assert result.provider_used.id == "p1"
        # Successful attempt is recorded too (CONCEPT §8.4).
        assert len(result.attempts) == 1
        assert result.attempts[0].error_type is None

    asyncio.run(_run())


def test_acall_first_provider_fails_uses_second():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", exception=ProviderOverloaded("529 overloaded"))
        adapter.set_response("p2", text="recovered")
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        result = await chain.acall("hi")

        assert result.output.content == "recovered"
        assert result.provider_used.id == "p2"
        assert len(result.attempts) == 2
        assert result.attempts[0].error_type == "ProviderOverloaded"
        assert result.attempts[0].fallback_eligible is True
        assert result.attempts[1].error_type is None

    asyncio.run(_run())


def test_acall_three_providers_secondary_succeeds_tertiary_unattempted():
    """Regression for R1 ``iterate()`` failover loop: with 3 providers and primary
    failing eligibly, secondary returns successfully and the tertiary is never built.

    Verifies the new one-tick-per-call contract: attempt order = priority-sorted
    rotation starting at the resolver-chosen index, each provider tried at most once
    per call. The tertiary ('p3') must NOT appear in attempts.
    """

    async def _run():
        adapter = _setup()
        adapter.set_response("p1", exception=ProviderOverloaded("529 overloaded"))
        adapter.set_response("p2", text="secondary served")
        adapter.set_response("p3", text="should not be reached")
        chain = RobustChain(
            providers=[_fake_spec("p1"), _fake_spec("p2"), _fake_spec("p3")],
        )

        result = await chain.acall("hi")

        assert result.output.content == "secondary served"
        assert result.provider_used.id == "p2"
        assert len(result.attempts) == 2  # tertiary never attempted
        assert [a.provider_id for a in result.attempts] == ["p1", "p2"]
        assert result.attempts[0].error_type == "ProviderOverloaded"
        assert result.attempts[0].fallback_eligible is True
        assert result.attempts[1].error_type is None

    asyncio.run(_run())


def test_acall_all_providers_fail_raises_all_failed():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", exception=ProviderOverloaded("529"))
        adapter.set_response("p2", exception=ProviderOverloaded("overloaded"))
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        try:
            await chain.acall("hi")
        except AllProvidersFailed as exc:
            assert len(exc.attempts) == 2
            assert all(a.fallback_eligible for a in exc.attempts)
            return
        raise AssertionError("expected AllProvidersFailed")

    asyncio.run(_run())


def test_acall_adapter_build_raw_exception_wraps_into_provider_model_creation_failed():
    """Adapter.build() raw SDK exceptions are wrapped into the typed
    ``ProviderModelCreationFailed`` contract; first wrapped failure is fallback
    eligible so the next provider is tried.

    Regression for the v0.5 backlog adapter-build error standardization —
    raw exceptions (ValueError, botocore ValidationException, etc.) must not
    leak past chain._build_model. External callers rely on the typed contract.
    """

    async def _run():
        adapter = _setup()
        adapter.set_response("p1", build_exception=ValueError("model id wrong"))
        adapter.set_response("p2", text="recovered")
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        result = await chain.acall("hi")

        assert result.output.content == "recovered"
        assert result.provider_used.id == "p2"
        assert len(result.attempts) == 2
        assert result.attempts[0].phase == "model_creation"
        assert result.attempts[0].error_type == "ProviderModelCreationFailed"
        assert result.attempts[0].fallback_eligible is True
        assert result.attempts[1].phase == "stream"
        assert result.attempts[1].error_type is None

    asyncio.run(_run())


def test_acall_all_adapter_build_failures_raise_all_providers_failed():
    """When every adapter.build() fails, AllProvidersFailed surfaces with
    ProviderModelCreationFailed-typed attempts (not raw exceptions).

    Verifies the full cause chain depth is preserved for debugging:
        AllProvidersFailed.__cause__       == last ProviderModelCreationFailed
        ProviderModelCreationFailed.__cause__ == raw SDK exception
    """

    async def _run():
        adapter = _setup()
        raw_p1 = ValueError("bad model id")
        raw_p2 = RuntimeError("region unsupported")
        adapter.set_response("p1", build_exception=raw_p1)
        adapter.set_response("p2", build_exception=raw_p2)
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        try:
            await chain.acall("hi")
        except AllProvidersFailed as exc:
            assert len(exc.attempts) == 2
            assert all(a.phase == "model_creation" for a in exc.attempts)
            assert all(a.error_type == "ProviderModelCreationFailed" for a in exc.attempts)
            assert all(a.fallback_eligible for a in exc.attempts)
            # Layer 1: AllProvidersFailed.__cause__ is the LAST wrapped error.
            assert isinstance(exc.__cause__, ProviderModelCreationFailed)
            # Layer 2: that wrap preserves the original raw SDK exception.
            assert exc.__cause__.__cause__ is raw_p2
            return
        raise AssertionError("expected AllProvidersFailed")

    asyncio.run(_run())


def test_astream_adapter_build_raw_exception_falls_over_then_recovers():
    """Streaming path (`_try_first_chunk`) wraps adapter.build() raw exceptions
    into ProviderModelCreationFailed and falls over to the next provider.

    Mirrors the non-streaming acall regression for the streaming code path —
    `_try_first_chunk` has its own catch (chain.py:531-541) and must follow
    the same wrap + fallback contract.
    """

    async def _run():
        adapter = _setup()
        adapter.set_response("p1", build_exception=ValueError("bad model id"))
        adapter.set_response("p2", chunks=["hi ", "there"])
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        chunks = [chunk async for chunk in chain.astream("ping")]
        assert "".join(c.content for c in chunks) == "hi there"

        result = chain.last_result
        assert result is not None
        assert result.provider_used.id == "p2"
        # p1 build wrapped → recorded model_creation attempt; p2 succeeded.
        assert any(
            a.phase == "model_creation" and a.error_type == "ProviderModelCreationFailed"
            for a in result.attempts
        )

    asyncio.run(_run())


def test_acall_first_token_timeout_records_phase_first_token_not_stream():
    """Non-streaming acall preserves the StreamExecutor's 'first_token' phase
    in AttemptRecord — does not collapse it to 'stream'.

    Regression for the chain.py:_failover_loop hardcoded 'stream' phase that
    masked first-token timeout from operational logs/metrics. First-token
    detection is a headline feature; attempt metadata must reflect it.
    """

    async def _run():
        adapter = _setup()
        # delay > first_token timeout forces ProviderTimeout(phase='first_token')
        adapter.set_response("p1", chunks=["x"], delay=1.0)
        adapter.set_response("p2", text="recovered")
        chain = RobustChain(
            providers=[_fake_spec("p1"), _fake_spec("p2")],
            timeouts=TimeoutConfig(
                per_provider=2.0, first_token=0.05, total=10.0, stream_cleanup=0.5
            ),
        )

        result = await chain.acall("hi")

        assert result.output.content == "recovered"
        assert result.provider_used.id == "p2"
        assert len(result.attempts) == 2
        assert result.attempts[0].error_type == "ProviderTimeout"
        assert result.attempts[0].phase == "first_token"
        assert result.attempts[0].fallback_eligible is True
        assert result.attempts[1].phase == "stream"
        assert result.attempts[1].error_type is None

    asyncio.run(_run())


def test_acall_total_timeout_raises_provider_timeout_phase_total():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", chunks=["x"], delay=10.0)
        chain = RobustChain(
            providers=[_fake_spec("p1")],
            timeouts=TimeoutConfig(
                per_provider=10.0, first_token=10.0, total=0.05, stream_cleanup=0.5
            ),
        )

        try:
            await chain.acall("hi")
        except ProviderTimeout as exc:
            assert exc.phase == "total"
            return
        raise AssertionError("expected ProviderTimeout(phase='total')")

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# ainvoke — Runnable surface + last_result
# ──────────────────────────────────────────────────────────────────────────────


def test_ainvoke_returns_base_message_only():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="ok")
        chain = RobustChain(providers=[_fake_spec("p1")])

        msg = await chain.ainvoke("hi")
        assert isinstance(msg, AIMessage)
        assert msg.content == "ok"

    asyncio.run(_run())


def test_ainvoke_metadata_via_last_result():
    async def _run():
        adapter = _setup()
        adapter.set_response(
            "p1", text="ok", usage={"input_tokens": 5, "output_tokens": 10, "total_tokens": 15}
        )
        chain = RobustChain(providers=[_fake_spec("p1")])

        await chain.ainvoke("hi")
        assert chain.last_result is not None
        assert chain.last_result.usage.input_tokens == 5
        assert chain.last_result.usage.output_tokens == 10
        assert chain.last_result.provider_used.id == "p1"

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# astream — yield + pre/post-commit semantics
# ──────────────────────────────────────────────────────────────────────────────


def test_astream_yields_chunks_in_order():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", chunks=["alpha", "beta", "gamma"])
        chain = RobustChain(providers=[_fake_spec("p1")])

        seen: list[str] = []
        async for chunk in chain.astream("hi"):
            if chunk.content:
                seen.append(str(chunk.content))

        assert seen == ["alpha", "beta", "gamma"]

    asyncio.run(_run())


def test_astream_pre_commit_silent_fallback():
    """First provider fails before any chunk; user sees only the second's stream."""

    async def _run():
        adapter = _setup()
        adapter.set_response("p1", exception=ProviderOverloaded("529"))
        adapter.set_response("p2", chunks=["good"])
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        seen: list[str] = []
        async for chunk in chain.astream("hi"):
            if chunk.content:
                seen.append(str(chunk.content))

        assert seen == ["good"]
        # last_result captures both attempts (failure + success).
        assert chain.last_result is not None
        assert len(chain.last_result.attempts) == 2
        assert chain.last_result.provider_used.id == "p2"

    asyncio.run(_run())


def test_astream_post_commit_raises_stream_interrupted():
    """Once chunks have flowed to the user, a mid-stream error never falls back."""

    async def _run():
        adapter = _setup()
        adapter.set_response(
            "p1", chunks=["a"], chunks_exception=RuntimeError("mid-stream failure")
        )
        adapter.set_response("p2", chunks=["never-used"])
        chain = RobustChain(providers=[_fake_spec("p1"), _fake_spec("p2")])

        seen: list[str] = []
        try:
            async for chunk in chain.astream("hi"):
                if chunk.content:
                    seen.append(str(chunk.content))
        except StreamInterrupted:
            assert seen == ["a"]
            return
        raise AssertionError("expected StreamInterrupted")

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# acall — ChatPromptTemplate / kwarg overrides / namespace
# ──────────────────────────────────────────────────────────────────────────────


def test_acall_with_chat_prompt_template_applies_inputs():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="ok")
        chain = RobustChain(providers=[_fake_spec("p1")])
        template = ChatPromptTemplate.from_messages(
            [("system", "be brief"), ("human", "tell me about {topic}")]
        )

        result = await chain.acall(template, topic="memcached")

        assert result.output.content == "ok"
        adapter.assert_inputs("p1", lambda msgs: any("memcached" in str(m.content) for m in msgs))

    asyncio.run(_run())


def test_acall_max_tokens_override_propagates_to_model_via_bind():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="ok")
        chain = RobustChain(providers=[_fake_spec("p1")])

        await chain.acall("hi", max_tokens=20)

        captured = adapter._call_kwargs.get("p1", [])
        assert captured, "expected at least one captured call"
        assert any(kw.get("max_tokens") == 20 for kw in captured)

    asyncio.run(_run())


def test_acall_temperature_override_propagates_to_model_via_bind():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="ok")
        chain = RobustChain(providers=[_fake_spec("p1")], temperature=0.1)

        await chain.acall("hi", temperature=0.7)

        captured = adapter._call_kwargs.get("p1", [])
        assert any(kw.get("temperature") == 0.7 for kw in captured)

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Sync surface — Runnable contract requires names but raises in v0.1
# ──────────────────────────────────────────────────────────────────────────────


def test_invoke_sync_raises_not_implemented():
    chain = RobustChain(providers=[_fake_spec("p1")])
    try:
        chain.invoke("hi")
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError")


def test_stream_sync_raises_not_implemented():
    chain = RobustChain(providers=[_fake_spec("p1")])
    try:
        chain.stream("hi")
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError")


# ──────────────────────────────────────────────────────────────────────────────
# Cumulative state — total_token_usage / total_cost
# ──────────────────────────────────────────────────────────────────────────────


def test_total_token_usage_accumulates_across_calls():
    async def _run():
        adapter = _setup()
        adapter.set_response(
            "p1",
            text="ok",
            usage={"input_tokens": 5, "output_tokens": 10, "total_tokens": 15},
        )
        chain = RobustChain(providers=[_fake_spec("p1")])

        await chain.acall("hi")
        await chain.acall("hi")

        assert chain.total_token_usage.input_tokens == 10
        assert chain.total_token_usage.output_tokens == 20
        assert chain.total_token_usage.total_tokens == 30

    asyncio.run(_run())


def test_total_cost_accumulates_when_pricing_set():
    async def _run():
        pricing = PricingSpec(input_per_1m=1.0, output_per_1m=2.0)
        adapter = _setup()
        adapter.set_response(
            "p1",
            text="ok",
            usage={
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "total_tokens": 2_000_000,
            },
        )
        chain = RobustChain(providers=[_fake_spec("p1", pricing=pricing)])

        await chain.acall("hi")
        await chain.acall("hi")

        assert chain.total_cost is not None
        assert chain.total_cost.input_cost == pytest.approx(2.0)
        assert chain.total_cost.output_cost == pytest.approx(4.0)
        assert chain.total_cost.total_cost == pytest.approx(6.0)

    asyncio.run(_run())


def test_total_cost_none_when_no_pricing():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="ok", usage={"input_tokens": 5, "output_tokens": 10})
        chain = RobustChain(providers=[_fake_spec("p1")])

        await chain.acall("hi")

        assert chain.total_cost is None

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# last_result contextvars isolation (concurrent calls)
# ──────────────────────────────────────────────────────────────────────────────


def test_last_result_isolated_per_concurrent_call():
    async def _run():
        adapter = _setup()
        adapter.set_response("p1", text="response")
        chain = RobustChain(providers=[_fake_spec("p1")])

        async def _one_call(_label: str) -> ChainResult | None:
            await chain.acall(_label)
            # Read in this task's contextvars scope.
            return chain.last_result

        a, b = await asyncio.gather(_one_call("a"), _one_call("b"))

        assert a is not None and b is not None
        assert a is not b  # distinct ChainResult instances per task

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# from_env factory
# ──────────────────────────────────────────────────────────────────────────────


def test_from_env_anthropic_only_active(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env-test-1234567890")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    chain = RobustChain.from_env(model_ids={"anthropic": "claude-haiku-4-5-20251001"})

    assert len(chain._providers) == 1
    assert chain._providers[0].type == "anthropic"
    assert chain._providers[0].api_key == "sk-ant-from-env-test-1234567890"


def test_from_env_zero_active_raises_no_providers_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    try:
        RobustChain.from_env(model_ids={"anthropic": "x", "openrouter": "y"})
    except NoProvidersConfigured:
        return
    raise AssertionError("expected NoProvidersConfigured")


def test_from_env_inactive_adapter_raises_provider_inactive(monkeypatch):
    """``redis`` is reserved for v0.2 backend support — calling it as a provider
    type raises ``ProviderInactive`` rather than silently passing through.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        RobustChain.from_env(model_ids={"redis": "ignored"})
    except ProviderInactive as exc:
        assert "redis" in str(exc).lower()
        return
    raise AssertionError("expected ProviderInactive for redis (still placeholder)")


def test_from_env_unknown_provider_type_logs_warning(monkeypatch, caplog):
    """Typo / unsupported provider types are skipped (existing contract) but
    must emit a WARN log so the user notices misconfiguration. Without this,
    a typo like ``antrophic`` silently produces ``NoProvidersConfigured`` with
    no hint at the cause.
    """
    import logging

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234567890")

    import contextlib

    typo = "antrophic"
    with (
        caplog.at_level(logging.WARNING, logger="robust_llm_chain.chain"),
        contextlib.suppress(Exception),
    ):
        RobustChain.from_env(model_ids={typo: "ignored", "anthropic": "claude-haiku"})

    matched = [r for r in caplog.records if typo in r.getMessage()]
    actual = [r.getMessage() for r in caplog.records]
    assert matched, f"expected WARN log mentioning {typo!r}; got {actual}"


def test_from_env_openai_active(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-1234567890")

    chain = RobustChain.from_env(model_ids={"openai": "gpt-4o-mini"})

    assert len(chain._providers) == 1
    assert chain._providers[0].type == "openai"
    assert chain._providers[0].api_key == "sk-openai-test-1234567890"


def test_from_env_bedrock_active_when_all_three_aws_envs_set(monkeypatch):
    for env_var in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST123456")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-test-value-1234")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    chain = RobustChain.from_env(model_ids={"bedrock": "anthropic.claude-haiku-4-5-20251001-v1:0"})

    assert len(chain._providers) == 1
    spec = chain._providers[0]
    assert spec.type == "bedrock"
    assert spec.region == "us-east-1"
    assert spec.aws_access_key_id == "AKIATEST123456"
    assert spec.aws_secret_access_key == "secret-test-value-1234"
    # No api_key — bedrock uses AWS creds.
    assert spec.api_key is None


def test_from_env_bedrock_skipped_when_aws_region_missing(monkeypatch):
    """Partial AWS creds (no AWS_REGION) → Bedrock provider skipped, not raised."""
    for env_var in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("AWS_REGION", raising=False)

    try:
        RobustChain.from_env(model_ids={"bedrock": "anthropic.claude-haiku-4-5-20251001-v1:0"})
    except NoProvidersConfigured:
        return
    raise AssertionError("expected NoProvidersConfigured when AWS_REGION absent")


def test_from_env_all_four_active(monkeypatch):
    """Cross-vendor + cross-model: all four providers active with their env vars."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    chain = RobustChain.from_env(
        model_ids={
            "anthropic": "claude-haiku-4-5-20251001",
            "openrouter": "anthropic/claude-haiku-4.5",
            "openai": "gpt-4o-mini",
            "bedrock": "anthropic.claude-haiku-4-5-20251001-v1:0",
        }
    )
    types = {p.type for p in chain._providers}
    assert types == {"anthropic", "openrouter", "openai", "bedrock"}


# ──────────────────────────────────────────────────────────────────────────────
# Multi-key registration — same provider type, different ids
# ──────────────────────────────────────────────────────────────────────────────


def test_multiple_specs_same_type_distinct_ids_round_robin():
    """Two ProviderSpecs with same ``type`` but different ``id`` are valid and
    independently selected by the round-robin resolver — supports patterns
    like primary + backup Anthropic keys, or Bedrock east + west regions."""

    async def _run():
        adapter = _setup()
        adapter.set_response("anthropic-direct-1", text="from key 1")
        adapter.set_response("anthropic-direct-2", text="from key 2")

        chain = RobustChain(
            providers=[
                ProviderSpec(
                    id="anthropic-direct-1",
                    type="fake",
                    model=ModelSpec(model_id="m"),
                    api_key="sk-key-1",
                ),
                ProviderSpec(
                    id="anthropic-direct-2",
                    type="fake",
                    model=ModelSpec(model_id="m"),
                    api_key="sk-key-2",
                ),
            ]
        )

        ids = []
        for _ in range(4):
            r = await chain.acall("hi")
            ids.append(r.provider_used.id)

        # Round-robin alternates between the two ids.
        assert ids == [
            "anthropic-direct-1",
            "anthropic-direct-2",
            "anthropic-direct-1",
            "anthropic-direct-2",
        ]

    asyncio.run(_run())


def test_multiple_same_type_chain_key_includes_all_ids():
    """The resolver key must distinguish chains with overlapping types/ids."""

    chain_a = RobustChain(
        providers=[
            ProviderSpec(id="a-1", type="fake", model=ModelSpec(model_id="m")),
            ProviderSpec(id="a-2", type="fake", model=ModelSpec(model_id="m")),
        ]
    )
    chain_b = RobustChain(
        providers=[
            ProviderSpec(id="a-1", type="fake", model=ModelSpec(model_id="m")),
            ProviderSpec(id="b-2", type="fake", model=ModelSpec(model_id="m")),
        ]
    )
    # Distinct chain keys → distinct backend counters.
    assert chain_a._make_chain_key() != chain_b._make_chain_key()
