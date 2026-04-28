"""In-process round-robin index backend (asyncio.Lock based).

Default backend when ``RobustChain(backend=None)`` is passed. Single-worker
safe; for multi-worker deployments use ``MemcachedBackend``.
"""

import asyncio
from collections import defaultdict


class LocalBackend:
    """asyncio.Lock-protected round-robin counter, keyed by string."""

    def __init__(self) -> None:
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def get_and_increment(self, key: str) -> int:
        """Return the current value for ``key`` and atomically add 1."""
        async with self._lock:
            current = self._counters[key]
            self._counters[key] = current + 1
            return current

    async def reset(self, key: str) -> None:
        """Delete the counter for ``key``. No-op if absent."""
        async with self._lock:
            self._counters.pop(key, None)

    async def close(self) -> None:
        """No external resources to release. Idempotent."""
        return
