"""Round-robin provider resolver.

Combines a ``list[ProviderSpec]`` with an ``IndexBackend`` to pick the next
provider for each call. Lower ``ProviderSpec.priority`` is preferred (sorted
ascending) — same convention as DNS MX records, cron priority, and Linux
``nice``: smaller number wins. The resolver delegates atomicity to the
backend — for multi-worker correctness use ``MemcachedBackend``.
"""

from typing import TYPE_CHECKING

from robust_llm_chain.errors import NoProvidersConfigured

if TYPE_CHECKING:
    from robust_llm_chain.backends import IndexBackend
    from robust_llm_chain.types import ProviderSpec


class ProviderResolver:
    """Picks the next provider via the configured ``IndexBackend``."""

    def __init__(
        self,
        providers: "list[ProviderSpec]",
        backend: "IndexBackend",
        key: str,
    ) -> None:
        if not providers:
            raise NoProvidersConfigured("ProviderResolver requires at least one ProviderSpec.")
        # Sort by priority ascending (lower priority first); stable for ties
        # so the user-listed order is preserved within the same priority.
        self._providers = sorted(providers, key=lambda p: p.priority)
        self._backend = backend
        self._key = key

    async def next(self) -> "ProviderSpec":
        """Return the next provider via ``backend.get_and_increment``.

        Raises:
            BackendUnavailable: When the backend cannot deliver an index
                (propagated unwrapped from the backend layer).
        """
        idx = await self._backend.get_and_increment(self._key)
        return self._providers[idx % len(self._providers)]

    async def iterate(self) -> "list[ProviderSpec]":
        """Return providers in attempt order for one call (failover sequence).

        One backend tick determines the starting point (preserves
        round-robin + worker coordination); the rest of the priority-sorted
        list follows in order, wrapping around. Each provider appears
        exactly once — this is the failover loop's contract: try every
        configured provider at most once per call, in priority order
        starting from the resolver-chosen entrypoint.

        Calling ``next()`` inside a per-call retry loop instead would race
        the global backend index with concurrent calls and could cause one
        call to retry the same provider while skipping another.

        Raises:
            BackendUnavailable: When the backend cannot deliver an index
                (propagated unwrapped from the backend layer).
        """
        n = len(self._providers)
        idx = await self._backend.get_and_increment(self._key)
        start = idx % n
        return self._providers[start:] + self._providers[:start]
