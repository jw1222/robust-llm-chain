"""``RobustChain`` — public orchestrator with Hybrid API.

Implements LangChain ``Runnable`` (``ainvoke`` / ``astream``) plus a
convenience ``acall`` that returns ``ChainResult`` directly. Round-robin
across configured providers via ``ProviderResolver`` + ``IndexBackend``;
streaming details (first-token timeout, bounded cleanup) live in
``StreamExecutor``.
"""

import asyncio
import contextvars
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from robust_llm_chain.builder import RobustChainBuilder

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, BaseMessageChunk, HumanMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from robust_llm_chain._security import sanitize_message
from robust_llm_chain.adapters import _ADAPTER_REGISTRY, get_adapter, register_adapter
from robust_llm_chain.adapters.anthropic import AnthropicAdapter
from robust_llm_chain.adapters.bedrock import BedrockAdapter
from robust_llm_chain.adapters.openai import OpenAIAdapter
from robust_llm_chain.adapters.openrouter import OpenRouterAdapter
from robust_llm_chain.backends import IndexBackend, LocalBackend
from robust_llm_chain.cost import compute_cost
from robust_llm_chain.errors import (
    AllProvidersFailed,
    NoProvidersConfigured,
    ProviderInactive,
    ProviderTimeout,
    StreamInterrupted,
    is_fallback_eligible,
)
from robust_llm_chain.resolver import ProviderResolver
from robust_llm_chain.stream import StreamExecutor, _accumulate_usage
from robust_llm_chain.types import (
    AttemptRecord,
    ChainResult,
    CostEstimate,
    ModelSpec,
    ProviderSpec,
    RobustChainInput,
    TimeoutConfig,
    TokenUsage,
)

#: Module-level logger for ``RobustChain.from_env`` and other classmethod paths
#: where the per-instance ``self._logger`` is not yet available.
_module_logger = logging.getLogger("robust_llm_chain.chain")

# Per-call ChainResult isolation. ``contextvars`` survive task hops, so
# concurrent ``asyncio.gather(chain.acall(...), chain.acall(...))`` calls do
# not see each other's results.
_LAST_RESULT: contextvars.ContextVar[ChainResult | None] = contextvars.ContextVar(
    "_LAST_RESULT", default=None
)

# Built-in adapters registered lazily when a chain instance is created. A
# placeholder dict ensures ``conftest._reset_adapter_registry`` snapshots them
# on first chain construction inside a test, then restores after.
_V01_ACTIVE_TYPES: frozenset[str] = frozenset({"anthropic", "openrouter", "openai", "bedrock"})
# Reserved for v0.2 — non-LLM adapter types still listed so ``from_env`` can
# raise a clear ``ProviderInactive`` instead of a confusing KeyError.
_V02_PLACEHOLDER_TYPES: frozenset[str] = frozenset({"redis"})

_TOTAL_TIMEOUT_BUFFER_SEC: float = 60.0
_TOTAL_TIMEOUT_CAP_SEC: float = 360.0


_BUILTIN_ADAPTERS: tuple[type, ...] = (
    AnthropicAdapter,
    OpenRouterAdapter,
    OpenAIAdapter,
    BedrockAdapter,
)


def _ensure_builtin_adapters_registered() -> None:
    """Register the four built-in adapters once per registry snapshot."""
    for adapter_cls in _BUILTIN_ADAPTERS:
        if adapter_cls.type not in _ADAPTER_REGISTRY:  # type: ignore[attr-defined]
            register_adapter(adapter_cls())


def _build_provider_spec(ptype: str, model_id: str, creds: dict[str, str]) -> ProviderSpec:
    """Map ``credentials_present`` output to the appropriate ``ProviderSpec`` shape.

    Bedrock returns ``aws_access_key_id`` / ``aws_secret_access_key`` /
    ``region``; everything else returns ``api_key``. ``from_env`` only sets
    the matching fields and leaves the rest at their defaults so the
    masking ``__repr__`` and adapter-side credential resolution stay clean.
    """
    if ptype == "bedrock":
        return ProviderSpec(
            id=ptype,
            type=ptype,
            model=ModelSpec(model_id=model_id),
            aws_access_key_id=creds.get("aws_access_key_id"),
            aws_secret_access_key=creds.get("aws_secret_access_key"),
            region=creds.get("region"),
        )
    return ProviderSpec(
        id=ptype,
        type=ptype,
        model=ModelSpec(model_id=model_id),
        api_key=creds.get("api_key"),
    )


class RobustChain(Runnable[RobustChainInput, BaseMessage]):
    """Cross-vendor failover chain. ``Runnable`` standard + ``acall`` convenience."""

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
        _ensure_builtin_adapters_registered()
        self._providers = list(providers)
        self._backend: IndexBackend = backend or LocalBackend()
        self._timeouts = timeouts or TimeoutConfig()
        self._temperature = temperature
        self._logger = logger or logging.getLogger("robust_llm_chain.chain")
        self._resolver = ProviderResolver(
            self._providers, self._backend, key=self._make_chain_key()
        )
        self._executor = StreamExecutor(
            first_token_timeout=self._timeouts.first_token,
            per_provider_timeout=self._timeouts.per_provider,
            stream_cleanup_timeout=self._timeouts.stream_cleanup,
        )
        self._total_usage = TokenUsage()
        self._total_cost: CostEstimate | None = None
        self._totals_lock = asyncio.Lock()

    # ── factory ─────────────────────────────────────────────────────────────

    @classmethod
    def builder(cls) -> "RobustChainBuilder":
        """Return a fluent builder. See ``robust_llm_chain.builder`` for usage.

        Example::

            chain = (
                RobustChain.builder()
                .add_anthropic(model="claude-haiku-4-5-20251001")
                .add_openrouter(model="anthropic/claude-haiku-4.5")
                .build()
            )
        """
        from robust_llm_chain.builder import RobustChainBuilder

        return RobustChainBuilder()

    @classmethod
    def from_env(
        cls,
        model_ids: dict[str, str],
        **kwargs: Any,
    ) -> "RobustChain":
        """Auto-build ``ProviderSpec`` list from standard env vars + ``model_ids``.

        For multi-key or multi-region patterns (e.g. two Anthropic keys, or
        Bedrock east + west), construct the ``ProviderSpec`` list explicitly
        and pass it to ``RobustChain(providers=[...])``. ``from_env`` covers
        the simple "one provider per type" path only.
        """
        _ensure_builtin_adapters_registered()
        providers: list[ProviderSpec] = []
        for ptype, model_id in model_ids.items():
            if ptype in _V02_PLACEHOLDER_TYPES:
                active_list = ", ".join(sorted(_V01_ACTIVE_TYPES))
                raise ProviderInactive(
                    f"{ptype} is reserved for v0.2 and not available in v0.1. "
                    f"Currently active provider types: {active_list}. "
                    f"Track v0.2 release for {ptype} support."
                )
            if ptype not in _V01_ACTIVE_TYPES:
                _module_logger.warning(
                    "from_env: unknown provider type %r — skipping. "
                    "Active types: %s. Possible typo?",
                    ptype,
                    sorted(_V01_ACTIVE_TYPES),
                )
                continue
            adapter = get_adapter(ptype)
            creds = adapter.credentials_present(os.environ)
            if creds is None:
                continue
            providers.append(_build_provider_spec(ptype, model_id, creds))
        if not providers:
            raise NoProvidersConfigured(
                "from_env() found no active providers. Check env vars + model_ids alignment."
            )
        return cls(providers, **kwargs)

    # ── Runnable async surface ──────────────────────────────────────────────

    async def ainvoke(
        self,
        input: RobustChainInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        """Run with cross-vendor failover; return ``BaseMessage`` only."""
        messages = self._normalize_runnable_input(input)
        result = await self._run_with_failover(messages, max_tokens=None, temperature=None)
        _LAST_RESULT.set(result)
        return result.output

    async def astream(
        self,
        input: RobustChainInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[BaseMessageChunk]:
        """Stream chunks with pre-commit silent fallback / post-commit StreamInterrupted."""
        messages = self._normalize_runnable_input(input)
        async for chunk in self._astream_with_failover(messages, max_tokens=None, temperature=None):
            yield chunk

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
        """Run with cross-vendor failover; return ``ChainResult`` directly."""
        messages = self._normalize_acall_input(prompt, template_inputs)
        result = await self._run_with_failover(
            messages, max_tokens=max_tokens, temperature=temperature
        )
        _LAST_RESULT.set(result)
        return result

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
        """Cumulative token usage across all calls."""
        return self._total_usage

    @property
    def total_cost(self) -> CostEstimate | None:
        """Cumulative cost (only when calls had ``ModelSpec.pricing``)."""
        return self._total_cost

    @property
    def last_result(self) -> ChainResult | None:
        """``ChainResult`` from the most recent call in this contextvars scope."""
        return _LAST_RESULT.get()

    # ── Internal helpers ────────────────────────────────────────────────────

    def _make_chain_key(self) -> str:
        ids = ",".join(p.id for p in self._providers)
        return f"chain:{ids}"

    def _compute_total_timeout(self) -> float:
        if self._timeouts.total is not None:
            return self._timeouts.total
        derived = self._timeouts.per_provider * len(self._providers) + _TOTAL_TIMEOUT_BUFFER_SEC
        return min(derived, _TOTAL_TIMEOUT_CAP_SEC)

    def _normalize_runnable_input(self, input: RobustChainInput) -> list[BaseMessage]:
        if isinstance(input, str):
            return [HumanMessage(content=input)]
        if isinstance(input, PromptValue):
            return list(input.to_messages())
        if isinstance(input, list):
            return input
        raise TypeError(f"Unsupported input type for ainvoke/astream: {type(input).__name__}")

    def _normalize_acall_input(
        self, prompt: Any, template_inputs: dict[str, Any]
    ) -> list[BaseMessage]:
        if isinstance(prompt, str):
            return [HumanMessage(content=prompt)]
        if isinstance(prompt, ChatPromptTemplate):
            return list(prompt.format_messages(**template_inputs))
        if isinstance(prompt, list):
            return prompt
        raise TypeError(f"Unsupported prompt type for acall: {type(prompt).__name__}")

    def _build_model(
        self,
        spec: ProviderSpec,
        max_tokens_override: int | None,
        temperature_override: float | None,
    ) -> BaseChatModel | Runnable[Any, Any]:
        adapter = get_adapter(spec.type)
        base = adapter.build(spec)
        bind_kwargs: dict[str, Any] = {}
        if max_tokens_override is not None:
            bind_kwargs["max_tokens"] = max_tokens_override
        # temperature: per-call override > chain default. (chain default is
        # always set, so temperature is always bound; this keeps behavior
        # consistent across providers regardless of their own defaults.)
        bind_kwargs["temperature"] = (
            temperature_override if temperature_override is not None else self._temperature
        )
        return base.bind(**bind_kwargs)

    def _record_attempt(
        self,
        spec: ProviderSpec,
        phase: str,
        start: float,
        exc: BaseException | None,
        eligible: bool,
    ) -> AttemptRecord:
        elapsed_ms = (time.monotonic() - start) * 1000
        return AttemptRecord(
            provider_id=spec.id,
            provider_type=spec.type,
            model_id=spec.model.model_id,
            phase=phase,  # type: ignore[arg-type]
            elapsed_ms=elapsed_ms,
            error_type=type(exc).__name__ if exc is not None else None,
            error_message=sanitize_message(str(exc)) if exc is not None else None,
            fallback_eligible=eligible,
            run_id=None,
        )

    async def _update_totals(self, result: ChainResult) -> None:
        async with self._totals_lock:
            self._total_usage += result.usage
            if result.cost is None:
                return
            self._total_cost = (
                result.cost if self._total_cost is None else self._total_cost + result.cost
            )

    async def _run_with_failover(
        self,
        messages: list[BaseMessage],
        *,
        max_tokens: int | None,
        temperature: float | None,
    ) -> ChainResult:
        """Non-streaming failover loop wrapped by ``total`` timeout."""
        start = time.monotonic()
        attempts: list[AttemptRecord] = []
        try:
            result = await asyncio.wait_for(
                self._failover_loop(messages, attempts, start, max_tokens, temperature),
                timeout=self._compute_total_timeout(),
            )
        except TimeoutError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            raise ProviderTimeout(phase="total", elapsed_ms=elapsed_ms) from e
        await self._update_totals(result)
        return result

    async def _failover_loop(
        self,
        messages: list[BaseMessage],
        attempts: list[AttemptRecord],
        start: float,
        max_tokens: int | None,
        temperature: float | None,
    ) -> ChainResult:
        last_error: BaseException | None = None
        for _ in range(len(self._providers)):
            spec = await self._resolver.next()
            attempt_start = time.monotonic()
            try:
                model = self._build_model(spec, max_tokens, temperature)
            except ProviderInactive:
                attempts.append(
                    self._record_attempt(spec, "model_creation", attempt_start, None, False)
                )
                raise
            try:
                output, usage = await self._executor.collect(model, messages)
            except Exception as exc:
                eligible = is_fallback_eligible(exc)
                attempts.append(self._record_attempt(spec, "stream", attempt_start, exc, eligible))
                last_error = exc
                if eligible:
                    continue
                raise
            attempts.append(self._record_attempt(spec, "stream", attempt_start, None, False))
            return ChainResult(
                input=messages,
                output=output,
                usage=usage,
                cost=compute_cost(spec.model, usage),
                provider_used=spec,
                model_used=spec.model,
                attempts=attempts,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
        raise AllProvidersFailed(attempts=attempts) from last_error

    async def _astream_with_failover(
        self,
        messages: list[BaseMessage],
        *,
        max_tokens: int | None,
        temperature: float | None,
    ) -> AsyncIterator[BaseMessageChunk]:
        start = time.monotonic()
        attempts: list[AttemptRecord] = []
        result = self._provisional_result(messages, attempts)
        _LAST_RESULT.set(result)

        last_error: BaseException | None = None
        for _ in range(len(self._providers)):
            spec = await self._resolver.next()
            first_chunk, agen, attempt_start, exc = await self._try_first_chunk(
                spec, messages, attempts, max_tokens, temperature
            )
            if first_chunk is None:
                last_error = exc
                continue
            # Post-commit phase. Ownership transferred to the caller.
            assert agen is not None
            try:
                async for chunk in self._post_commit_stream(
                    first_chunk, agen, spec, result, attempt_start, attempts, start
                ):
                    yield chunk
            finally:
                # StreamExecutor.stream's own finally handles aclose.
                pass
            await self._update_totals(result)
            return

        raise AllProvidersFailed(attempts=attempts) from last_error

    def _provisional_result(
        self, messages: list[BaseMessage], attempts: list[AttemptRecord]
    ) -> ChainResult:
        first_spec = self._providers[0]
        return ChainResult(
            input=messages,
            output=AIMessage(content=""),
            usage=TokenUsage(),
            cost=None,
            provider_used=first_spec,
            model_used=first_spec.model,
            attempts=attempts,
            elapsed_ms=0.0,
        )

    async def _try_first_chunk(
        self,
        spec: ProviderSpec,
        messages: list[BaseMessage],
        attempts: list[AttemptRecord],
        max_tokens: int | None,
        temperature: float | None,
    ) -> "tuple[BaseMessageChunk | None, AsyncIterator[BaseMessageChunk] | None, float, BaseException | None]":  # noqa: E501
        attempt_start = time.monotonic()
        try:
            model = self._build_model(spec, max_tokens, temperature)
        except ProviderInactive:
            attempts.append(
                self._record_attempt(spec, "model_creation", attempt_start, None, False)
            )
            raise
        agen = self._executor.stream(model, messages)
        try:
            first = await agen.__anext__()
        except ProviderTimeout as exc:
            attempts.append(self._record_attempt(spec, "first_token", attempt_start, exc, True))
            return None, None, attempt_start, exc
        except StopAsyncIteration as exc:
            empty = RuntimeError("empty stream")
            attempts.append(self._record_attempt(spec, "stream", attempt_start, empty, True))
            return None, None, attempt_start, exc
        except Exception as exc:
            eligible = is_fallback_eligible(exc)
            attempts.append(self._record_attempt(spec, "first_token", attempt_start, exc, eligible))
            if eligible:
                return None, None, attempt_start, exc
            raise
        return first, agen, attempt_start, None

    async def _post_commit_stream(
        self,
        first_chunk: BaseMessageChunk,
        agen: AsyncIterator[BaseMessageChunk],
        spec: ProviderSpec,
        result: ChainResult,
        attempt_start: float,
        attempts: list[AttemptRecord],
        start: float,
    ) -> AsyncIterator[BaseMessageChunk]:
        """Yield chunks once first one arrives. Mid-stream errors → StreamInterrupted."""
        result.provider_used = spec
        result.model_used = spec.model
        accumulated: BaseMessageChunk = first_chunk
        usage = TokenUsage()
        _accumulate_usage(usage, first_chunk)
        yield first_chunk
        try:
            async for chunk in agen:
                accumulated = accumulated + chunk
                _accumulate_usage(usage, chunk)
                yield chunk
        except Exception as exc:
            attempts.append(self._record_attempt(spec, "stream", attempt_start, exc, False))
            result.output = accumulated
            result.usage = usage
            result.elapsed_ms = (time.monotonic() - start) * 1000
            raise StreamInterrupted(
                f"stream interrupted after first chunk on provider={spec.id}"
            ) from exc
        attempts.append(self._record_attempt(spec, "stream", attempt_start, None, False))
        result.output = accumulated
        result.usage = usage
        result.cost = compute_cost(spec.model, usage)
        result.elapsed_ms = (time.monotonic() - start) * 1000
