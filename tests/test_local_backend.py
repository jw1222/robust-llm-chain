"""Unit tests for ``robust_llm_chain.backends.local.LocalBackend``.

Phase 3 scope: atomic increment + concurrent contention + key isolation.
"""

import asyncio

from robust_llm_chain.backends.local import LocalBackend


def test_local_backend_get_and_increment_starts_at_zero():
    async def _run():
        backend = LocalBackend()
        first = await backend.get_and_increment("k")
        second = await backend.get_and_increment("k")
        assert first == 0
        assert second == 1

    asyncio.run(_run())


def test_local_backend_concurrent_100_returns_unique_indices():
    async def _run():
        backend = LocalBackend()
        results = await asyncio.gather(*(backend.get_and_increment("k") for _ in range(100)))
        assert sorted(results) == list(range(100))

    asyncio.run(_run())


def test_local_backend_separate_keys_are_independent():
    async def _run():
        backend = LocalBackend()
        await backend.get_and_increment("k1")
        await backend.get_and_increment("k1")
        assert await backend.get_and_increment("k2") == 0
        assert await backend.get_and_increment("k1") == 2

    asyncio.run(_run())


def test_local_backend_reset_clears_key():
    async def _run():
        backend = LocalBackend()
        await backend.get_and_increment("k")
        await backend.get_and_increment("k")
        await backend.reset("k")
        assert await backend.get_and_increment("k") == 0

    asyncio.run(_run())


def test_local_backend_close_idempotent():
    async def _run():
        backend = LocalBackend()
        await backend.close()
        await backend.close()  # second call must not raise

    asyncio.run(_run())
