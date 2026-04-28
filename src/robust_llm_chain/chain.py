"""``RobustChain`` — public orchestrator with Hybrid API.

Implements LangChain ``Runnable`` (``ainvoke`` / ``astream``) plus a
convenience ``acall`` that returns ``ChainResult`` directly. Phase 4 (T10)
fills in the actual logic; this Phase 3 stub keeps the constructor + public
API surface stable so importers don't break.
"""

import contextvars
import logging
from collections.abc import AsyncIterator
from typing import Any, NoReturn

from langchain_core.messages import BaseMessage, BaseMessageChunk
from langchain_core.runnables import Runnable, RunnableConfig

from robust_llm_chain.backends import IndexBackend, LocalBackend
from robust_llm_chain.errors import NoProvidersConfigured
from robust_llm_chain.types import (
    ChainResult,
    CostEstimate,
    ProviderSpec,
    RobustChainInput,
    TimeoutConfig,
    TokenUsage,
)

# Per-call ChainResult isolation. ``contextvars`` survive task hops, so
# concurrent ``asyncio.gather(chain.acall(...), chain.acall(...))`` calls do
# not see each other's results.
_LAST_RESULT: contextvars.ContextVar[ChainResult | None] = contextvars.ContextVar(
    "_LAST_RESULT", default=None
)


class RobustChain(Runnable[RobustChainInput, BaseMessage]):
    """Cross-vendor failover chain. LangChain ``Runnable`` + convenience methods.

    Phase 4 (T10) wires up the resolver / stream executor / fallback loop.
    """

    def __init__(
        self,
        providers: list[ProviderSpec],
        *,
        backend: IndexBackend | None = None,
        timeouts: TimeoutConfig | None = None,
        temperature: float = 0.1,
        logger: logging.Logger | None = None,
    ) -> None:
        if not providers:
            raise NoProvidersConfigured("RobustChain requires at least one ProviderSpec.")
        self._providers = list(providers)
        self._backend: IndexBackend = backend or LocalBackend()
        self._timeouts = timeouts or TimeoutConfig()
        self._temperature = temperature
        self._logger = logger or logging.getLogger("robust_llm_chain.chain")
        self._total_usage = TokenUsage()
        self._total_cost: CostEstimate | None = None

    # ── factory ─────────────────────────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        model_ids: dict[str, str],
        **kwargs: Any,
    ) -> "RobustChain":
        """Auto-build ``ProviderSpec`` list from standard env vars + ``model_ids``.

        Phase 4 (T10) implementation. Active condition: env vars present AND
        the provider type appears in ``model_ids``. Zero-active raises
        ``NoProvidersConfigured``.
        """
        raise NotImplementedError("RobustChain.from_env is implemented in Phase 4 (T10).")

    # ── Runnable async surface ──────────────────────────────────────────────

    async def ainvoke(
        self,
        input: RobustChainInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        """Run with cross-vendor failover; return ``BaseMessage``. Phase 4 (T10)."""
        raise NotImplementedError("RobustChain.ainvoke is implemented in Phase 4 (T10).")

    async def astream(
        self,
        input: RobustChainInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[BaseMessageChunk]:
        """Stream chunks; pre-commit silent fallback / post-commit ``StreamInterrupted``.

        Phase 4 (T10) implementation.
        """
        raise NotImplementedError("RobustChain.astream is implemented in Phase 4 (T10).")
        # Required so the function is recognized as an async generator.
        if False:  # pragma: no cover
            yield

    # ── Convenience: acall (returns ChainResult directly) ───────────────────

    async def acall(
        self,
        prompt: Any,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        config: RunnableConfig | None = None,
        **template_inputs: Any,
    ) -> ChainResult:
        """Run with cross-vendor failover; return ``ChainResult`` directly.

        Phase 4 (T10) implementation.
        """
        raise NotImplementedError("RobustChain.acall is implemented in Phase 4 (T10).")

    # ── Sync surface — Runnable contract requires the names. ────────────────

    def invoke(self, *args: Any, **kwargs: Any) -> NoReturn:
        """Sync invocation is not supported in v0.1."""
        raise NotImplementedError("v0.1 supports async only. Use ainvoke() or acall().")

    def stream(self, *args: Any, **kwargs: Any) -> NoReturn:
        """Sync streaming is not supported in v0.1."""
        raise NotImplementedError("v0.1 supports async only. Use astream() or acall().")

    # ── Read-only state ─────────────────────────────────────────────────────

    @property
    def total_token_usage(self) -> TokenUsage:
        """Cumulative token usage across all calls. ``asyncio.Lock``-protected."""
        return self._total_usage

    @property
    def total_cost(self) -> CostEstimate | None:
        """Cumulative cost (only when every call had ``ModelSpec.pricing``)."""
        return self._total_cost

    @property
    def last_result(self) -> ChainResult | None:
        """``ChainResult`` from the most recent call in this contextvars scope."""
        return _LAST_RESULT.get()
