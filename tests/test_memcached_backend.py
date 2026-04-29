"""Unit tests for ``robust_llm_chain.backends.memcached``.

Phase 4 (T11). Uses an in-memory ``MemcacheClient`` to exercise the
add+incr seeding loop without spinning up real memcached. Failure cases
verify ``fail-closed`` semantics (REVIEW_DECISIONS Round 2 후속 결정).
"""

import asyncio
import inspect

from robust_llm_chain.backends.memcached import MemcacheClient, MemcachedBackend
from robust_llm_chain.errors import BackendUnavailable

# ──────────────────────────────────────────────────────────────────────────────
# In-memory MemcacheClient — covers happy path + concurrency
# ──────────────────────────────────────────────────────────────────────────────


class _InMemoryClient:
    """Minimal MemcacheClient satisfying the Protocol.

    Uses an ``asyncio.Lock`` to keep ``add`` / ``incr`` atomic so that
    concurrent ``backend.get_and_increment`` calls actually receive distinct
    indices (mirrors real memcached's atomicity guarantees).
    """

    def __init__(self) -> None:
        self._store: dict[bytes, bytes] = {}
        self._lock = asyncio.Lock()
        self.close_count = 0

    async def get(self, key: bytes) -> bytes | None:
        async with self._lock:
            return self._store.get(key)

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        async with self._lock:
            if key in self._store:
                return False
            self._store[key] = value
            return True

    async def incr(self, key: bytes, increment: int = 1) -> int | None:
        async with self._lock:
            if key not in self._store:
                return None
            new = int(self._store[key]) + increment
            self._store[key] = str(new).encode()
            return new

    async def delete(self, key: bytes) -> bool:
        async with self._lock:
            self._store.pop(key, None)
            return True

    async def close(self) -> None:
        self.close_count += 1


# ──────────────────────────────────────────────────────────────────────────────
# Protocol shape
# ──────────────────────────────────────────────────────────────────────────────


def test_protocol_defines_minimum_async_interface():
    methods = {m for m in dir(MemcacheClient) if not m.startswith("_")}
    assert {"get", "add", "incr", "delete", "close"}.issubset(methods)


def test_protocol_methods_are_coroutines():
    for name in ("get", "add", "incr", "delete", "close"):
        attr = getattr(MemcacheClient, name)
        assert inspect.iscoroutinefunction(attr), f"{name} should be async"


# ──────────────────────────────────────────────────────────────────────────────
# Happy path — seed + incr semantics
# ──────────────────────────────────────────────────────────────────────────────


def test_first_call_returns_zero_and_seeds_counter():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client)

        first = await backend.get_and_increment("k")
        assert first == 0
        # Subsequent calls return monotonic increasing indices.
        assert await backend.get_and_increment("k") == 1
        assert await backend.get_and_increment("k") == 2

    asyncio.run(_run())


def test_separate_keys_have_independent_counters():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client)

        await backend.get_and_increment("k1")
        await backend.get_and_increment("k1")
        # k2 starts fresh.
        assert await backend.get_and_increment("k2") == 0
        assert await backend.get_and_increment("k1") == 2

    asyncio.run(_run())


def test_concurrent_calls_yield_unique_indices():
    """Real memcached atomicity guarantee — workers never see duplicate idx."""

    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client)
        results = await asyncio.gather(*(backend.get_and_increment("k") for _ in range(50)))
        assert sorted(results) == list(range(50))

    asyncio.run(_run())


def test_wrap_at_modular_resets_to_zero():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client, wrap_at=3)

        observed = [await backend.get_and_increment("k") for _ in range(7)]
        # 0, 1, 2, 0, 1, 2, 0
        assert observed == [0, 1, 2, 0, 1, 2, 0]

    asyncio.run(_run())


def test_key_prefix_is_applied_to_storage():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client, key_prefix="myapp:rr")
        await backend.get_and_increment("chain:p1,p2")
        # Verify the stored key carries the prefix.
        assert any(k.startswith(b"myapp:rr") for k in client._store)

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Fail-closed semantics — connection / timeout failures raise BackendUnavailable
# ──────────────────────────────────────────────────────────────────────────────


class _HangingClient:
    """Every operation hangs forever — used to drive timeout paths."""

    async def get(self, key: bytes) -> bytes | None:
        await asyncio.sleep(60)
        return None

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        await asyncio.sleep(60)
        return False

    async def incr(self, key: bytes, increment: int = 1) -> int | None:
        await asyncio.sleep(60)
        return None

    async def delete(self, key: bytes) -> bool:
        await asyncio.sleep(60)
        return False

    async def close(self) -> None:
        pass


class _ConnectionErrorClient:
    """Every operation raises OSError to mimic memcached down."""

    async def get(self, key: bytes) -> bytes | None:
        raise OSError("connection refused")

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        raise OSError("connection refused")

    async def incr(self, key: bytes, increment: int = 1) -> int | None:
        raise OSError("connection refused")

    async def delete(self, key: bytes) -> bool:
        raise OSError("connection refused")

    async def close(self) -> None:
        return


def test_timeout_raises_backend_unavailable():
    async def _run():
        backend = MemcachedBackend(client=_HangingClient(), timeout_seconds=0.05)
        try:
            await backend.get_and_increment("k")
        except BackendUnavailable as exc:
            assert exc.__cause__ is not None  # original cause preserved
            return
        raise AssertionError("expected BackendUnavailable on timeout")

    asyncio.run(_run())


def test_connection_error_raises_backend_unavailable():
    async def _run():
        backend = MemcachedBackend(client=_ConnectionErrorClient())
        try:
            await backend.get_and_increment("k")
        except BackendUnavailable as exc:
            assert isinstance(exc.__cause__, OSError)
            return
        raise AssertionError("expected BackendUnavailable on connection error")

    asyncio.run(_run())


def test_no_silent_fallback_to_local_backend():
    """fail-closed (REVIEW_DECISIONS Round 2 후속): never auto-fallback."""

    async def _run():
        backend = MemcachedBackend(client=_ConnectionErrorClient())
        try:
            await backend.get_and_increment("k")
        except BackendUnavailable:
            return
        raise AssertionError("library MUST NOT silently swap to LocalBackend")

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ──────────────────────────────────────────────────────────────────────────────


def test_close_invokes_client_close():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client)
        await backend.close()
        assert client.close_count == 1

    asyncio.run(_run())


def test_close_idempotent():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client)
        await backend.close()
        await backend.close()  # second call must not raise

    asyncio.run(_run())


def test_reset_deletes_counter():
    async def _run():
        client = _InMemoryClient()
        backend = MemcachedBackend(client=client)
        await backend.get_and_increment("k")
        await backend.get_and_increment("k")
        await backend.reset("k")
        # After reset, counter restarts at 0.
        assert await backend.get_and_increment("k") == 0

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Fail-closed: BackendUnavailable on transport / SDK errors
# ──────────────────────────────────────────────────────────────────────────────


class _UnreachableClient:
    """Client where every operation raises ``OSError`` — simulates dead memcached."""

    async def get(self, key: bytes) -> bytes | None:
        raise OSError("connection refused")

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        raise OSError("connection refused")

    async def incr(self, key: bytes, increment: int = 1) -> int | None:
        raise OSError("connection refused")

    async def delete(self, key: bytes) -> bool:
        raise OSError("connection refused")

    async def close(self) -> None:
        return None


def test_get_and_increment_raises_backend_unavailable_on_oserror():
    """Memcached transport failure must raise ``BackendUnavailable`` (fail-closed)."""

    async def _run():
        backend = MemcachedBackend(client=_UnreachableClient())
        try:
            await backend.get_and_increment("k")
        except BackendUnavailable as exc:
            assert "memcached unreachable" in str(exc)
            return
        raise AssertionError("expected BackendUnavailable")

    asyncio.run(_run())


def test_reset_raises_backend_unavailable_on_oserror():
    """Reset must also fail-closed when memcached is unreachable."""

    async def _run():
        backend = MemcachedBackend(client=_UnreachableClient())
        try:
            await backend.reset("k")
        except BackendUnavailable as exc:
            assert "memcached unreachable" in str(exc)
            return
        raise AssertionError("expected BackendUnavailable")

    asyncio.run(_run())


class _IncrAlwaysNoneClient(_InMemoryClient):
    """incr returns None (key never exists) — simulates the cannot-seed race.

    The backend should retry seed via add; if add also reports the key already
    exists AND incr still returns None, raise BackendUnavailable rather than
    spinning silently.
    """

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        return False  # always lose the seeding race

    async def incr(self, key: bytes, increment: int = 1) -> int | None:
        return None  # key still does not exist


def test_get_and_increment_raises_when_seed_fails_after_lost_race():
    """If add loses the race AND retry-incr still returns None, fail-closed."""

    async def _run():
        backend = MemcachedBackend(client=_IncrAlwaysNoneClient())
        try:
            await backend.get_and_increment("k")
        except BackendUnavailable as exc:
            assert "neither exists after seed nor accepts incr" in str(exc)
            return
        raise AssertionError("expected BackendUnavailable")

    asyncio.run(_run())
