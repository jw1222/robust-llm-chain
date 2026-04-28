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


def test_from_env_inactive_v0_1_adapter_raises_provider_inactive(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    try:
        RobustChain.from_env(model_ids={"bedrock": "anthropic.claude-haiku-4-5"})
    except ProviderInactive as exc:
        assert "bedrock" in str(exc).lower()
        return
    raise AssertionError("expected ProviderInactive for bedrock in v0.1")
