"""Unit tests for ``robust_llm_chain.resolver.ProviderResolver``.

The resolver combines a static provider list with an ``IndexBackend`` to
produce a per-call attempt sequence via :meth:`ProviderResolver.iterate`.

Two roles per call (v0.4.0+):

* RR (over user-listed order) selects the *first* provider this call attempts.
* Priority-sorted (lower wins) determines the *fallback* order after the first
  provider fails — independent of RR start.
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
# iterate() — RR start (user-listed) + priority-sorted fallback
# ──────────────────────────────────────────────────────────────────────────────


def test_iterate_advances_starting_point_per_call():
    """Each call ticks the backend once; RR start advances along user-listed order."""

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


def test_iterate_rr_start_then_priority_fallback():
    """RR picks first provider; remaining follow priority order (lower wins).

    With ``[A(p=0), B(p=1), C(p=2)]`` (user-listed = priority order):

    * call 1 → start A, fallback [B, C] → ``[A, B, C]``
    * call 2 → start B, fallback [A, C] → ``[B, A, C]``
    * call 3 → start C, fallback [A, B] → ``[C, A, B]``
    """

    async def _run():
        providers = [_spec("p0", priority=0), _spec("p1", priority=1), _spec("p2", priority=2)]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        assert [s.id for s in await resolver.iterate()] == ["p0", "p1", "p2"]
        assert [s.id for s in await resolver.iterate()] == ["p1", "p0", "p2"]
        assert [s.id for s in await resolver.iterate()] == ["p2", "p0", "p1"]

    asyncio.run(_run())


def test_iterate_user_listed_rr_independent_of_priority():
    """RR rotates over user-listed order; fallback uses priority order.

    Builder added [B, A, C] but priority is A=0, B=1, C=2.
    RR cycles in user-listed order (B→A→C); fallback is priority-sorted.
    """

    async def _run():
        providers = [_spec("B", priority=1), _spec("A", priority=0), _spec("C", priority=2)]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        # RR start B → fallback by priority [A, C]
        assert [s.id for s in await resolver.iterate()] == ["B", "A", "C"]
        # RR start A → fallback by priority [B, C]
        assert [s.id for s in await resolver.iterate()] == ["A", "B", "C"]
        # RR start C → fallback by priority [A, B]
        assert [s.id for s in await resolver.iterate()] == ["C", "A", "B"]

    asyncio.run(_run())


def test_iterate_concurrent_calls_get_distinct_rotations():
    """Regression: per-call snapshot prevents concurrent acalls from racing the index.

    With per-iter ``next()`` (the v0.2 implementation), two concurrent
    acalls could consume each other's indices and cause one call to retry
    the same provider while skipping another. ``iterate()`` ticks the
    backend exactly once per call, so each call's attempt sequence is a
    stable RR start + priority-ordered fallback.
    """

    async def _run():
        providers = [_spec("a"), _spec("b")]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        seq_a, seq_b = await asyncio.gather(resolver.iterate(), resolver.iterate())
        ids_a = [s.id for s in seq_a]
        ids_b = [s.id for s in seq_b]
        assert sorted(ids_a) == ["a", "b"]
        assert sorted(ids_b) == ["a", "b"]
        # Each sequence is complete (no skips) and distinct (different starting points).
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


def test_priority_ascending_orders_fallback_lower_first():
    """Fallback uses ascending priority (lower wins, DNS MX / cron / nice convention).

    User-listed order is preserved by RR — first call's start is the first
    user-listed spec; the fallback list is priority-sorted regardless.
    """

    async def _run():
        providers = [
            _spec("primary", priority=0),
            _spec("tertiary", priority=10),
            _spec("secondary", priority=5),
        ]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        # RR start = primary (first user-listed); fallback by priority [secondary, tertiary]
        assert [s.id for s in await resolver.iterate()] == ["primary", "secondary", "tertiary"]
        # RR start = tertiary (second user-listed); fallback by priority [primary, secondary]
        assert [s.id for s in await resolver.iterate()] == ["tertiary", "primary", "secondary"]
        # RR start = secondary (third user-listed); fallback by priority [primary, tertiary]
        assert [s.id for s in await resolver.iterate()] == ["secondary", "primary", "tertiary"]

    asyncio.run(_run())


def test_iterate_dedups_by_identity_not_equality():
    """Two ProviderSpec instances that are value-equal AND identity-distinct are both reachable.

    Identity-based dedup (``p is not start``) — not ``p == start`` and not
    ``p.id != start.id`` — is what keeps both specs reachable when a user
    constructs duplicates that differ only in compare=False fields (api_key,
    aws_access_key_id, aws_secret_access_key). An equality-based filter would
    silently drop one — the test below would fail under ``p == start`` because
    ``a1 == a2`` is True (compared fields match).
    """

    async def _run():
        # Same id, type, model, priority → value-equal under dataclass __eq__
        # (api_key has compare=False, so different keys don't break equality).
        a1 = ProviderSpec(
            id="anthropic",
            type="fake",
            model=ModelSpec(model_id="claude-haiku"),
            api_key="key-1",
            priority=0,
        )
        a2 = ProviderSpec(
            id="anthropic",
            type="fake",
            model=ModelSpec(model_id="claude-haiku"),
            api_key="key-2",
            priority=0,
        )
        # Locks the regression contract: value-equal but identity-distinct.
        assert a1 == a2 and a1 is not a2
        resolver = ProviderResolver([a1, a2], LocalBackend(), key="k")
        seq1 = await resolver.iterate()
        seq2 = await resolver.iterate()
        # Each call returns BOTH instances (no silent drop), in different orders.
        assert len(seq1) == 2 and len(seq2) == 2
        assert {id(s) for s in seq1} == {id(a1), id(a2)}
        assert {id(s) for s in seq2} == {id(a1), id(a2)}
        # RR start advances even though specs are value-equal.
        assert seq1[0] is a1 and seq2[0] is a2

    asyncio.run(_run())


def test_iterate_same_priority_preserves_user_listed_order_in_fallback():
    """Stable sort: same-priority providers keep user-listed order in fallback list."""

    async def _run():
        providers = [
            _spec("a", priority=5),
            _spec("b", priority=5),
            _spec("c", priority=5),
        ]
        resolver = ProviderResolver(providers, LocalBackend(), key="k")
        # All same priority → fallback follows user-listed order.
        # call 1: start a, fallback [b, c]
        assert [s.id for s in await resolver.iterate()] == ["a", "b", "c"]
        # call 2: start b, fallback [a, c]
        assert [s.id for s in await resolver.iterate()] == ["b", "a", "c"]
        # call 3: start c, fallback [a, b]
        assert [s.id for s in await resolver.iterate()] == ["c", "a", "b"]

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
