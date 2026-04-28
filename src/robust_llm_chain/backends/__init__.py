"""Round-robin index storage backends.

Public surface: ``IndexBackend`` Protocol + concrete implementations
(``LocalBackend``, ``MemcachedBackend``). Users implementing a custom
backend (DynamoDB, Cloudflare KV, etc.) only need to satisfy the Protocol.
"""

from typing import Protocol

from robust_llm_chain.backends.local import LocalBackend
from robust_llm_chain.backends.memcached import MemcacheClient, MemcachedBackend


class IndexBackend(Protocol):
    """Round-robin index storage abstraction.

    Implementations must provide atomic ``get_and_increment`` semantics so
    multi-worker deployments can share a single index without races.
    """

    async def get_and_increment(self, key: str) -> int:
        """Return the current index for ``key`` and atomically increment it.

        The returned value is the index *before* incrementing (zero-based on
        first call). Implementations must guarantee race-free behavior even
        in distributed environments. On failure, raise
        :class:`robust_llm_chain.errors.BackendUnavailable`.
        """
        ...

    async def reset(self, key: str) -> None:
        """Delete the index for ``key`` (test/operations utility)."""
        ...

    async def close(self) -> None:
        """Release resources. Idempotent."""
        ...


__all__ = ["IndexBackend", "LocalBackend", "MemcacheClient", "MemcachedBackend"]
