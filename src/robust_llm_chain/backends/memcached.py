"""Memcached-backed round-robin index for multi-worker deployments.

Depends on the ``MemcacheClient`` Protocol (not a concrete library), so any
async memcached client (e.g. ``aiomcache.Client``) satisfies it via duck
typing. CODING_STYLE §1.6 D — DIP.

Failure semantics: **fail-closed** (REVIEW_DECISIONS Round 2 후속 결정).
On any backend failure, raises ``BackendUnavailable``. The library does not
silently fall back to ``LocalBackend`` because that would break the
worker-coordinated round-robin guarantee that is the library's
differentiator.
"""

import asyncio
import contextlib
from typing import Final, Protocol

from robust_llm_chain.errors import BackendUnavailable

#: Default per-call timeout for memcached operations.
_DEFAULT_TIMEOUT_SEC: Final[float] = 3.0
#: Default TTL for the round-robin counter (30 days).
_DEFAULT_TTL_SEC: Final[int] = 86400 * 30
#: Default modulo for the counter (1 Mi).
_DEFAULT_WRAP_AT: Final[int] = 1024 * 1024
#: Default key prefix.
_DEFAULT_KEY_PREFIX: Final[str] = "rlc:rr"


class MemcacheClient(Protocol):
    """Minimal async Memcached client interface (duck-typed).

    ``aiomcache.Client`` satisfies this Protocol natively. Other libraries
    can be wrapped to match.
    """

    async def get(self, key: bytes) -> bytes | None:
        """Return the value for ``key``, or ``None`` if absent."""
        ...

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        """Set ``key`` only if absent. Returns ``False`` if it already exists.

        This is the atomic seeding primitive used to bootstrap the counter.
        """
        ...

    async def incr(self, key: bytes, increment: int = 1) -> int | None:
        """Atomically add ``increment`` to ``key``'s current value.

        Returns the new value, or ``None`` if the key does not exist (the
        caller should seed it via ``add`` and retry).
        """
        ...

    async def delete(self, key: bytes) -> bool:
        """Delete ``key``. Idempotent — returns ``True`` even if absent."""
        ...

    async def close(self) -> None:
        """Release client resources. Idempotent."""
        ...


class MemcachedBackend:
    """Worker-coordinated round-robin via Memcached ``add`` + ``incr`` semantics.

    Algorithm: try ``incr`` first (cheap atomic). If the key does not exist,
    seed it via ``add(b"1")`` to claim index ``0``. If ``add`` loses the race
    to another worker, ``incr`` again to receive the next slot. This is
    race-free without requiring CAS support.

    Failure (timeout / connection) raises ``BackendUnavailable`` — the
    library does NOT auto-fallback to ``LocalBackend``.
    """

    def __init__(
        self,
        *,
        client: MemcacheClient,
        key_prefix: str = _DEFAULT_KEY_PREFIX,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SEC,
        ttl_seconds: int = _DEFAULT_TTL_SEC,
        wrap_at: int = _DEFAULT_WRAP_AT,
    ) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._timeout_seconds = timeout_seconds
        self._ttl_seconds = ttl_seconds
        self._wrap_at = wrap_at

    async def get_and_increment(self, key: str) -> int:
        """Return the next round-robin index for ``key`` (zero-based, modulo ``wrap_at``).

        Raises:
            BackendUnavailable: Memcached unreachable, timing out, or
                returning unexpected ``None`` after both ``incr`` and ``add``
                attempts. The library does not fall back to ``LocalBackend``.
        """
        full_key = self._full_key(key)
        timeout = self._timeout_seconds
        try:
            new_val = await asyncio.wait_for(self._client.incr(full_key, 1), timeout=timeout)
            if new_val is None:
                # Key absent — seed at 1 so the caller's slot is index 0.
                seeded = await asyncio.wait_for(
                    self._client.add(full_key, b"1", self._ttl_seconds), timeout=timeout
                )
                if seeded:
                    return 0
                # Lost the race; another worker seeded. Retry incr.
                new_val = await asyncio.wait_for(
                    self._client.incr(full_key, 1), timeout=timeout
                )
                if new_val is None:
                    raise BackendUnavailable(
                        "memcached counter neither exists after seed nor accepts incr"
                    )
        except (TimeoutError, OSError) as e:
            raise BackendUnavailable(f"memcached unreachable: {e}") from e
        # ``incr`` returns the value AFTER incrementing; convert to the
        # zero-based index BEFORE incrementing.
        return (new_val - 1) % self._wrap_at

    async def reset(self, key: str) -> None:
        """Delete the counter for ``key``. Idempotent."""
        try:
            await asyncio.wait_for(
                self._client.delete(self._full_key(key)), timeout=self._timeout_seconds
            )
        except (TimeoutError, OSError) as e:
            raise BackendUnavailable(f"memcached unreachable: {e}") from e

    async def close(self) -> None:
        """Release client resources. Idempotent — swallows close errors."""
        with contextlib.suppress(Exception):
            await self._client.close()

    # ── Internal ────────────────────────────────────────────────────────────

    def _full_key(self, key: str) -> bytes:
        return f"{self._key_prefix}:{key}".encode()
