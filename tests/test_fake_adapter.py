"""Unit tests for ``robust_llm_chain.testing.FakeAdapter``.

Phase 3 scope: text response, exception, install/registry behavior.
Phase 4 expansion: streaming chunks / first-token delay / usage_metadata /
install replacement semantics.
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from robust_llm_chain.adapters import _ADAPTER_REGISTRY, get_adapter
from robust_llm_chain.testing import FakeAdapter, ProviderOverloaded, install_fake_adapter
from robust_llm_chain.types import ModelSpec, ProviderSpec


def _spec(provider_id: str = "p1") -> ProviderSpec:
    return ProviderSpec(
        id=provider_id,
        type="fake",
        model=ModelSpec(model_id="m"),
    )


# ──────────────────────────────────────────────────────────────────────────────
# install_fake_adapter — explicit registration only
# ──────────────────────────────────────────────────────────────────────────────


def test_import_alone_does_not_register():
    """Importing FakeAdapter must not auto-register (CONCEPT §15)."""
    assert "fake" not in _ADAPTER_REGISTRY


def test_install_registers_into_registry():
    install_fake_adapter()
    assert "fake" in _ADAPTER_REGISTRY


def test_install_returns_the_registered_instance():
    a = install_fake_adapter()
    assert get_adapter("fake") is a


def test_install_can_register_prebuilt_instance():
    custom = FakeAdapter()
    returned = install_fake_adapter(custom)
    assert returned is custom
    assert get_adapter("fake") is custom


# ──────────────────────────────────────────────────────────────────────────────
# Scenario behavior — ainvoke path via _agenerate
# ──────────────────────────────────────────────────────────────────────────────


def test_text_scenario_returns_configured_response():
    async def _run():
        adapter = install_fake_adapter()
        adapter.set_response("p1", text="hello world")
        model = adapter.build(_spec("p1"))

        result = await model.ainvoke([HumanMessage(content="hi")])
        assert result.content == "hello world"

    asyncio.run(_run())


def test_exception_scenario_raises():
    async def _run():
        adapter = install_fake_adapter()
        adapter.set_response("p1", exception=ProviderOverloaded("529"))
        model = adapter.build(_spec("p1"))

        try:
            await model.ainvoke([HumanMessage(content="hi")])
        except ProviderOverloaded as e:
            assert "529" in str(e)
        else:
            raise AssertionError("expected ProviderOverloaded")

    asyncio.run(_run())


def test_credentials_present_returns_empty_dict():
    """FakeAdapter is always 'active' so from_env can pick it up."""
    adapter = FakeAdapter()
    assert adapter.credentials_present({}) == {}


def test_assert_inputs_accepts_when_call_matches():
    async def _run():
        adapter = install_fake_adapter()
        adapter.set_response("p1", text="ok")
        model = adapter.build(_spec("p1"))
        await model.ainvoke([HumanMessage(content="probe")])

        adapter.assert_inputs(
            "p1",
            lambda msgs: msgs[0].content == "probe",
        )

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Streaming scenarios — astream path via _astream
# ──────────────────────────────────────────────────────────────────────────────


def test_streams_chunks_in_configured_order():
    """Configured chunks must be yielded in order. (LangChain may append a
    trailing empty chunk via its callback wrapper — filter those out.)"""

    async def _run():
        adapter = install_fake_adapter()
        adapter.set_response("p1", chunks=["alpha", "beta", "gamma"])
        model = adapter.build(_spec("p1"))

        received = [
            str(chunk.content)
            async for chunk in model.astream([HumanMessage(content="hi")])
            if chunk.content
        ]
        assert received == ["alpha", "beta", "gamma"]

    asyncio.run(_run())


def test_first_token_delay_blocks_until_elapsed():
    """``delay`` simulates a pending provider — first chunk only after wait."""

    async def _run():
        adapter = install_fake_adapter()
        adapter.set_response("p1", chunks=["x"], delay=0.1)
        model = adapter.build(_spec("p1"))

        start = time.monotonic()
        async for _chunk in model.astream([HumanMessage(content="hi")]):
            elapsed = time.monotonic() - start
            assert elapsed >= 0.1, f"first chunk arrived too early: {elapsed:.3f}s"
            return

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# usage_metadata propagation
# ──────────────────────────────────────────────────────────────────────────────


def test_usage_metadata_attached_to_ainvoke_response():
    async def _run():
        adapter = install_fake_adapter()
        adapter.set_response("p1", text="hello", usage={"input_tokens": 10, "output_tokens": 20})
        model = adapter.build(_spec("p1"))

        result = await model.ainvoke([HumanMessage(content="hi")])
        usage = result.usage_metadata
        assert usage is not None
        assert usage["input_tokens"] == 10
        assert usage["output_tokens"] == 20
        # total_tokens is auto-derived when caller omits it.
        assert usage["total_tokens"] == 30

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# install_fake_adapter — repeated calls keep registry single-entry
# ──────────────────────────────────────────────────────────────────────────────


def test_install_twice_replaces_with_latest_instance():
    """Second ``install_fake_adapter`` overrides the first under the same ``type``."""
    first = install_fake_adapter()
    second = install_fake_adapter()
    assert first is not second
    assert get_adapter("fake") is second
    # Registry still has exactly one entry for "fake".
    assert sum(1 for k in _ADAPTER_REGISTRY if k == "fake") == 1
