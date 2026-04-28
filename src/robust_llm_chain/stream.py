"""Three-phase streaming executor.

Phase 1: ``first_token`` wait (bounded by ``first_token_timeout``).
Phase 2: chunk pump (cumulative wall-clock bounded by ``per_provider_timeout``).
Phase 3: ``aclose()`` cleanup (bounded by ``stream_cleanup_timeout``;
         failures here must not block the caller).

Used by ``chain.py`` for both ``astream`` (yield raw chunks to the caller)
and ``ainvoke`` / ``acall`` (collect chunks into a single ``BaseMessage`` so
all paths benefit from the ``first_token`` timeout).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage, BaseMessageChunk
from langchain_core.runnables import Runnable

from robust_llm_chain.errors import ProviderTimeout
from robust_llm_chain.types import TokenUsage

logger = logging.getLogger(__name__)


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
        model: Runnable[Any, Any],
        messages: list[BaseMessage],
    ) -> AsyncIterator[BaseMessageChunk]:
        """Yield chunks subject to first-token + per-provider timeouts.

        Raises:
            ProviderTimeout(phase="first_token"): No chunk arrived within
                ``first_token_timeout``.
            ProviderTimeout(phase="stream"): Cumulative wall clock exceeded
                ``per_provider_timeout`` after the first chunk.
        """
        agen = model.astream(messages)
        start = time.monotonic()
        try:
            # Phase 1 — first token.
            try:
                first = await asyncio.wait_for(agen.__anext__(), timeout=self._first_token_timeout)
            except TimeoutError as e:
                elapsed_ms = (time.monotonic() - start) * 1000
                raise ProviderTimeout(phase="first_token", elapsed_ms=elapsed_ms) from e
            except StopAsyncIteration:
                # Provider yielded zero chunks — treat as empty stream.
                return
            yield first

            # Phase 2 — subsequent chunks bounded by per_provider deadline.
            deadline = start + self._per_provider_timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    raise ProviderTimeout(phase="stream", elapsed_ms=elapsed_ms)
                try:
                    chunk = await asyncio.wait_for(agen.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    break
                except TimeoutError as e:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    raise ProviderTimeout(phase="stream", elapsed_ms=elapsed_ms) from e
                yield chunk
        finally:
            # Phase 3 — bounded cleanup. Failures (including aclose hangs) must
            # not propagate; the caller should not be punished by SDK quirks.
            await _bounded_aclose(agen, cleanup_timeout=self._stream_cleanup_timeout)

    async def collect(
        self,
        model: Runnable[Any, Any],
        messages: list[BaseMessage],
    ) -> tuple[BaseMessage, TokenUsage]:
        """Run ``stream`` under the hood and combine chunks into a single message.

        Used by ``ainvoke`` / ``acall`` so they benefit from the
        ``first_token`` differentiator. Returns the accumulated message plus
        the summed ``TokenUsage`` extracted from chunk ``usage_metadata``.
        """
        accumulated: BaseMessageChunk | None = None
        usage = TokenUsage()
        async for chunk in self.stream(model, messages):
            accumulated = chunk if accumulated is None else accumulated + chunk
            _accumulate_usage(usage, chunk)

        if accumulated is None:
            accumulated = AIMessageChunk(content="")
        message: BaseMessage = accumulated
        return message, usage


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _bounded_aclose(agen: AsyncIterator[BaseMessageChunk], cleanup_timeout: float) -> None:
    """``aclose()`` with a bounded wait. Swallow timeouts and SDK errors.

    LangChain's ``BaseChatModel.astream`` returns an iterator wrapper rather
    than a raw ``AsyncGenerator``; not all wrappers expose ``aclose``. Skip
    silently when absent.
    """
    aclose = getattr(agen, "aclose", None)
    if aclose is None:
        return
    with contextlib.suppress(TimeoutError, Exception):
        await asyncio.wait_for(aclose(), timeout=cleanup_timeout)


def _accumulate_usage(usage: TokenUsage, chunk: BaseMessageChunk) -> None:
    """Pull token counts off ``chunk.usage_metadata`` and add them to ``usage``."""
    metadata = getattr(chunk, "usage_metadata", None)
    if not metadata:
        return
    usage += TokenUsage(
        input_tokens=int(metadata.get("input_tokens", 0)),
        output_tokens=int(metadata.get("output_tokens", 0)),
        cache_read_tokens=int(metadata.get("cache_read_input_tokens", 0)),
        cache_write_tokens=int(metadata.get("cache_creation_input_tokens", 0)),
        total_tokens=int(metadata.get("total_tokens", 0)),
    )
