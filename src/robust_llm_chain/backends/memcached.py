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

from typing import Protocol


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

        This is the atomic-lock primitive used by the round-robin counter.
        """
        ...

    async def delete(self, key: bytes) -> bool:
        """Delete ``key``. Idempotent — returns ``True`` even if absent."""
        ...

    async def close(self) -> None:
        """Release client resources. Idempotent."""
        ...


class MemcachedBackend:
    """Worker-coordinated round-robin via Memcached ``add`` semantics.

    Phase 4 (T11) implementation. Stub raises ``NotImplementedError`` so
    Phase 3 mypy/ruff still pass while the file is reachable from the
    public ``backends`` package.
    """

    def __init__(
        self,
        *,
        client: MemcacheClient,
        key_prefix: str = "rlc:rr",
        timeout_seconds: float = 3.0,
        ttl_seconds: int = 86400 * 30,
        wrap_at: int = 1024 * 1024,
    ) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._timeout_seconds = timeout_seconds
        self._ttl_seconds = ttl_seconds
        self._wrap_at = wrap_at

    async def get_and_increment(self, key: str) -> int:
        """Atomic get-and-increment via Memcached ``add`` loop. Phase 4 (T11)."""
        raise NotImplementedError(
            "MemcachedBackend.get_and_increment is implemented in Phase 4 (T11)."
        )

    async def reset(self, key: str) -> None:
        """Delete the counter for ``key``. Phase 4 (T11)."""
        raise NotImplementedError("MemcachedBackend.reset is implemented in Phase 4 (T11).")

    async def close(self) -> None:
        """Release client resources. Phase 4 (T11)."""
        raise NotImplementedError("MemcachedBackend.close is implemented in Phase 4 (T11).")
