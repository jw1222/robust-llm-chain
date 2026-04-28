"""Three-phase streaming executor.

Phase 1: ``first_token`` wait → Phase 2: chunk collect → Phase 3: cleanup
with bounded ``aclose()`` timeout. Used by ``chain.py`` for both
``ainvoke`` (chunks → BaseMessage collect) and ``astream`` (yield raw).

Phase 4 (T8) implementation. Stub keeps the module importable.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage, BaseMessageChunk

    from robust_llm_chain.types import TokenUsage


class StreamExecutor:
    """Owns the per-call streaming policy (timeouts + cleanup)."""

    def __init__(
        self,
        *,
        first_token_timeout: float,
        per_provider_timeout: float,
        stream_cleanup_timeout: float,
    ) -> None:
        self._first_token_timeout = first_token_timeout
        self._per_provider_timeout = per_provider_timeout
        self._stream_cleanup_timeout = stream_cleanup_timeout

    async def stream(
        self,
        model: "BaseChatModel",
        messages: "list[BaseMessage]",
    ) -> AsyncIterator["BaseMessageChunk"]:
        """Yield chunks; raise ``ProviderTimeout`` on first-token / stream timeout.

        Phase 4 (T8) implementation.
        """
        raise NotImplementedError("StreamExecutor.stream is implemented in Phase 4 (T8).")
        # Required so the function is recognized as an async generator.
        if False:  # pragma: no cover
            yield

    async def collect(
        self,
        model: "BaseChatModel",
        messages: "list[BaseMessage]",
    ) -> "tuple[BaseMessage, TokenUsage]":
        """Run streaming under the hood and collect into a single ``BaseMessage``.

        Used by ``ainvoke`` / ``acall`` so they benefit from the
        ``first_token`` differentiator. Phase 4 (T8) implementation.
        """
        raise NotImplementedError("StreamExecutor.collect is implemented in Phase 4 (T8).")
