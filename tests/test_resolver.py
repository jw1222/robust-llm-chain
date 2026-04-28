"""Unit tests for ``robust_llm_chain.resolver.ProviderResolver``.

Phase 4 (T9). Combines a static provider list with an ``IndexBackend`` for
round-robin selection. Priority sort + backend error propagation are the
non-trivial paths.
"""

import asyncio

from robust_llm_chain.backends.local import LocalBackend
from robust_llm_chain.errors import BackendUnavailable, NoProvidersConfigured
from robust_llm_chain.resolver import ProviderResolver
from robust_llm_chain.types import ModelSpec, ProviderSpec


def _spec(provider_id: str, *, priority: int = 0) -> ProviderSpec:
    return ProviderSpec(
        id=provider_id,
        type="fake",
        model=ModelSpec(model_id=f"m-{provider_id}"),
        priority=priority,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Round-robin
# ──────────────────────────────────────────────────────────────────────────────


def test_round_robin_yields_in_listed_order():
    async def _run():
        providers = [_spec("a"), _spec("b"), _spec("c")]
        resolver = ProviderResolver(providers, LocalBackend(), key="chain-x")
        ids = [(await resolver.next()).id for _ in range(3)]
        assert ids == ["a", "b", "c"]

    asyncio.run(_run())


def test_round_robin_wraps_modulo_n():
    async def _run():
        providers = [_spec("a"), _spec("b"), _spec("c")]
        resolver = ProviderResolver(providers, LocalBackend(), key="chain-x")
        ids = [(await resolver.next()).id for _ in range(7)]
        assert ids == ["a", "b", "c", "a", "b", "c", "a"]

    asyncio.run(_run())


def test_separate_keys_have_independent_indices():
    """Two resolvers using the same backend but different keys do not share state."""

    async def _run():
        backend = LocalBackend()
        r1 = ProviderResolver([_spec("a"), _spec("b")], backend, key="chain-1")
        r2 = ProviderResolver([_spec("a"), _spec("b")], backend, key="chain-2")

        assert (await r1.next()).id == "a"
        assert (await r1.next()).id == "b"
        # r2 starts fresh — different key.
        assert (await r2.next()).id == "a"

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Priority sort
# ──────────────────────────────────────────────────────────────────────────────


def test_priority_descending_sorts_higher_first():
    async def _run():
        providers = [_spec("low", priority=0), _spec("high", priority=10), _spec("mid", priority=5)]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        ids = [(await resolver.next()).id for _ in range(3)]
        assert ids == ["high", "mid", "low"]

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Empty providers
# ──────────────────────────────────────────────────────────────────────────────


def test_empty_providers_raises_no_providers_configured():
    try:
        ProviderResolver([], LocalBackend(), key="k")
    except NoProvidersConfigured:
        return
    raise AssertionError("expected NoProvidersConfigured")


# ──────────────────────────────────────────────────────────────────────────────
# Backend failure propagation
# ──────────────────────────────────────────────────────────────────────────────


class _FailingBackend:
    async def get_and_increment(self, key: str) -> int:
        raise BackendUnavailable("simulated memcached down")

    async def reset(self, key: str) -> None:
        return

    async def close(self) -> None:
        return


def test_backend_unavailable_propagates_unwrapped():
    async def _run():
        resolver = ProviderResolver([_spec("a")], _FailingBackend(), key="k")
        try:
            await resolver.next()
        except BackendUnavailable:
            return
        raise AssertionError("expected BackendUnavailable propagation")

    asyncio.run(_run())
