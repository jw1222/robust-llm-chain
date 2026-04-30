"""Round-robin start + priority-ordered fallback resolver.

Two roles, one per call:

* **Round-robin** picks the *first* provider this call attempts — distributes
  initial-attempt traffic across providers via the configured ``IndexBackend``.
* **Priority** orders the *fallback sequence* after the first provider fails —
  the remaining providers are tried in ascending priority order (lower wins,
  DNS MX / cron / Linux ``nice`` convention). Within the same priority,
  user-listed order is preserved.

For ``[A(p=0), B(p=1), C(p=2)]`` the attempt sequences cycle:

* call 1: ``A → B → C`` (RR picked A; fallback by priority)
* call 2: ``B → A → C`` (RR picked B; fallback A then C)
* call 3: ``C → A → B`` (RR picked C; fallback A then B)

The resolver delegates atomicity to the backend — for multi-worker correctness
use ``MemcachedBackend``.
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
        # Two views: RR rotates over user-listed order; fallback is priority-sorted.
        # Stable sort preserves user-listed order within the same priority.
        self._providers = list(providers)
        self._priority_sorted = sorted(providers, key=lambda p: p.priority)
        self._backend = backend
        self._key = key

    async def iterate(self) -> "list[ProviderSpec]":
        """Return providers in attempt order for one call (failover sequence).

        One backend tick selects the *starting* provider (RR over the
        user-listed order). The remaining providers follow in *priority*
        order (lower wins). Each provider appears exactly once — try every
        configured provider at most once per call.

        One tick per call (not per attempt) keeps concurrent ``acall``
        invocations from racing the global index — a per-attempt tick could
        let one call retry the same provider while skipping another.

        For ``[A(p=0), B(p=1), C(p=2)]``:

        * tick 0 → start ``A`` → ``[A, B, C]`` (fallback B then C)
        * tick 1 → start ``B`` → ``[B, A, C]`` (fallback A then C)
        * tick 2 → start ``C`` → ``[C, A, B]`` (fallback A then B)

        Raises:
            BackendUnavailable: When the backend cannot deliver an index
                (propagated unwrapped from the backend layer).
        """
        n = len(self._providers)
        idx = await self._backend.get_and_increment(self._key)
        start = self._providers[idx % n]
        # 'is' (not '!='): two ProviderSpec instances may share the same `id`
        # (or be otherwise value-equal); identity dedups exactly the RR-picked
        # entry while preserving every other configured spec in the fallback.
        fallbacks = [p for p in self._priority_sorted if p is not start]
        return [start, *fallbacks]
