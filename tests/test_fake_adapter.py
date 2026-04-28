"""Unit tests for ``robust_llm_chain.testing.FakeAdapter``.

Phase 3 scope: text response, exception, install/registry behavior.
Streaming chunks / delays land in Phase 4 alongside the stream executor.
"""

import asyncio

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
