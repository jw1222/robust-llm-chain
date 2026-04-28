"""Round-robin provider resolver.

Combines a ``list[ProviderSpec]`` with an ``IndexBackend`` to pick the next
provider for each call. Phase 4 (T9) implementation.
"""

from typing import TYPE_CHECKING

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
        self._providers = providers
        self._backend = backend
        self._key = key

    async def next(self) -> "ProviderSpec":
        """Return the next provider via ``backend.get_and_increment``.

        Phase 4 (T9) implementation. Sorts by ``priority`` (descending),
        applies modular wrap based on the index returned by the backend.
        """
        raise NotImplementedError("ProviderResolver.next is implemented in Phase 4 (T9).")
