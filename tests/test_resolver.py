"""Unit tests for ``robust_llm_chain.resolver.ProviderResolver``.

The resolver combines a static provider list with an ``IndexBackend`` to
produce a per-call attempt sequence via :meth:`ProviderResolver.iterate`.
Priority sort + backend error propagation are the non-trivial paths.
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
# iterate() — round-robin starting point + wrap-around rotation
# ──────────────────────────────────────────────────────────────────────────────


def test_iterate_advances_starting_point_per_call():
    """Each call ticks the backend once; rotation start advances by one."""

    async def _run():
        providers = [_spec("a"), _spec("b"), _spec("c")]
        resolver = ProviderResolver(providers, LocalBackend(), key="chain-x")
        starts = [(await resolver.iterate())[0].id for _ in range(3)]
        assert starts == ["a", "b", "c"]

    asyncio.run(_run())


def test_iterate_wraps_modulo_n():
    """7 calls, 3 providers → starts cycle a/b/c/a/b/c/a."""

    async def _run():
        providers = [_spec("a"), _spec("b"), _spec("c")]
        resolver = ProviderResolver(providers, LocalBackend(), key="chain-x")
        starts = [(await resolver.iterate())[0].id for _ in range(7)]
        assert starts == ["a", "b", "c", "a", "b", "c", "a"]

    asyncio.run(_run())


def test_iterate_returns_full_rotation_starting_at_index():
    """One backend tick picks the start; the rest of the priority-sorted list follows."""

    async def _run():
        providers = [_spec("p0", priority=0), _spec("p1", priority=1), _spec("p2", priority=2)]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        assert [s.id for s in await resolver.iterate()] == ["p0", "p1", "p2"]
        assert [s.id for s in await resolver.iterate()] == ["p1", "p2", "p0"]
        assert [s.id for s in await resolver.iterate()] == ["p2", "p0", "p1"]

    asyncio.run(_run())


def test_iterate_concurrent_calls_get_distinct_rotations():
    """Regression: per-call snapshot prevents concurrent acalls from racing the index.

    With per-iter ``next()`` (the v0.2 implementation), two concurrent
    acalls could consume each other's indices and cause one call to retry
    the same provider while skipping another. ``iterate()`` ticks the
    backend exactly once per call, so each call's attempt sequence is a
    stable rotation.
    """

    async def _run():
        providers = [_spec("a"), _spec("b")]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        seq_a, seq_b = await asyncio.gather(resolver.iterate(), resolver.iterate())
        ids_a = [s.id for s in seq_a]
        ids_b = [s.id for s in seq_b]
        assert sorted(ids_a) == ["a", "b"]
        assert sorted(ids_b) == ["a", "b"]
        # Each rotation is complete (no skips) and distinct (different starting points).
        assert ids_a != ids_b

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Independent backend keys
# ──────────────────────────────────────────────────────────────────────────────


def test_separate_keys_have_independent_indices():
    """Two resolvers using the same backend but different keys do not share state."""

    async def _run():
        backend = LocalBackend()
        r1 = ProviderResolver([_spec("a"), _spec("b")], backend, key="chain-1")
        r2 = ProviderResolver([_spec("a"), _spec("b")], backend, key="chain-2")

        assert (await r1.iterate())[0].id == "a"
        assert (await r1.iterate())[0].id == "b"
        # r2 starts fresh — different key.
        assert (await r2.iterate())[0].id == "a"

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Priority sort
# ──────────────────────────────────────────────────────────────────────────────


def test_priority_ascending_sorts_lower_first():
    """Lower priority value = higher precedence (DNS MX / cron / nice convention)."""

    async def _run():
        providers = [
            _spec("primary", priority=0),
            _spec("tertiary", priority=10),
            _spec("secondary", priority=5),
        ]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        # First iterate() starts at idx 0 = lowest-priority spec in sorted list.
        assert [s.id for s in await resolver.iterate()] == ["primary", "secondary", "tertiary"]

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
            await resolver.iterate()
        except BackendUnavailable:
            return
        raise AssertionError("expected BackendUnavailable propagation")

    asyncio.run(_run())
