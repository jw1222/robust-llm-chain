"""``FakeAdapter`` for unit tests — simulates provider responses without SDK calls.

Used by the library's own tests and exposed publicly so downstream users can
write integration tests against ``RobustChain`` without paying for real API
calls. CONCEPT §15.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr

from robust_llm_chain.adapters import register_adapter
from robust_llm_chain.types import ProviderSpec


class ProviderOverloaded(Exception):
    """Stand-in for provider 5xx/529 used in fallback-eligible test scenarios."""


@dataclass
class FakeScenario:
    """Per-provider response configuration."""

    text: str | None = None
    exception: BaseException | None = None
    chunks: list[str] | None = None
    delay: float = 0.0
    usage: dict[str, int] | None = None
    # Raised after the configured ``chunks`` have all been yielded — used to
    # simulate post-commit streaming failures (StreamInterrupted scenarios).
    chunks_exception: BaseException | None = None
    # Raised by ``FakeAdapter.build()`` to simulate SDK validation/config
    # errors (model id wrong, region wrong, etc.) — used to verify that
    # ``chain._build_model`` wraps these into ``ProviderModelCreationFailed``.
    build_exception: BaseException | None = None


@dataclass
class FakeAdapter:
    """In-memory adapter that returns scripted responses by ``provider.id``."""

    type: ClassVar[str] = "fake"
    _scenarios: dict[str, FakeScenario] = field(default_factory=dict)
    _calls: dict[str, list[list[BaseMessage]]] = field(default_factory=dict)
    # Per-provider invocation kwargs (e.g. ``max_tokens`` / ``temperature``
    # forwarded by ``RobustChain._build_model`` via ``model.bind(...)``).
    _call_kwargs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def set_response(
        self,
        provider_id: str,
        *,
        text: str | None = None,
        exception: BaseException | None = None,
        chunks: list[str] | None = None,
        delay: float = 0.0,
        usage: dict[str, int] | None = None,
        chunks_exception: BaseException | None = None,
        build_exception: BaseException | None = None,
    ) -> None:
        """Configure the response for ``provider_id``.

        Args:
            provider_id: Matches ``ProviderSpec.id``.
            text: Returned by ``ainvoke`` / collected by ``astream`` if
                ``chunks`` is None.
            exception: Raised when the provider is invoked.
            chunks: Sequence yielded by ``astream``.
            delay: Sleep before the first chunk / response (simulates pending).
            usage: Returned as ``usage_metadata``.
            chunks_exception: Raised after all configured ``chunks`` have been
                yielded — simulates post-commit streaming failures.
            build_exception: Raised by ``build()`` to simulate SDK validation
                or config errors (model id wrong, region wrong, etc.).
        """
        self._scenarios[provider_id] = FakeScenario(
            text=text,
            exception=exception,
            chunks=chunks,
            delay=delay,
            usage=usage,
            chunks_exception=chunks_exception,
            build_exception=build_exception,
        )

    def assert_inputs(
        self,
        provider_id: str,
        predicate: Callable[[list[BaseMessage]], bool],
    ) -> None:
        """Assert ``predicate`` is True for at least one captured call."""
        calls = self._calls.get(provider_id, [])
        assert calls, f"FakeAdapter received no calls for provider_id={provider_id!r}"
        assert any(predicate(c) for c in calls), (
            f"No call to {provider_id!r} satisfied the predicate"
        )

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct a ``_FakeChatModel`` bound to ``spec.id``'s scenario."""
        scenario = self._scenarios.get(spec.id, FakeScenario())
        if scenario.build_exception is not None:
            raise scenario.build_exception
        model = _FakeChatModel(scenario=scenario, provider_id=spec.id)
        # Bind the adapter's sinks via PrivateAttr so capture survives
        # Pydantic's model construction (which would otherwise replace
        # mutable field defaults with copies).
        model._calls_sink = self._calls
        model._kwargs_sink = self._call_kwargs
        return model

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """``FakeAdapter`` is always active — returns an empty dict."""
        return {}


def install_fake_adapter(adapter: FakeAdapter | None = None) -> FakeAdapter:
    """Register a ``FakeAdapter`` instance with the global registry.

    The library does not auto-register the fake adapter at import time —
    callers must invoke this explicitly (CONCEPT §15 — TDD isolation).

    Args:
        adapter: Optional pre-built adapter. A new ``FakeAdapter()`` is
            created when ``None``.

    Returns:
        The registered adapter (so callers can configure scenarios).
    """
    a = adapter or FakeAdapter()
    register_adapter(a)
    return a


# ──────────────────────────────────────────────────────────────────────────────
# Internal — fake LangChain BaseChatModel
# ──────────────────────────────────────────────────────────────────────────────


class _FakeChatModel(BaseChatModel):
    """Minimal LangChain ``BaseChatModel`` driven by a ``FakeScenario``.

    Implements ``_agenerate`` (for ainvoke) and ``_astream`` (for astream).
    Sync paths intentionally raise ``NotImplementedError``.
    """

    scenario: FakeScenario
    provider_id: str
    _calls_sink: dict[str, list[list[BaseMessage]]] = PrivateAttr(default_factory=dict)
    _kwargs_sink: dict[str, list[dict[str, Any]]] = PrivateAttr(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("Use async path (_agenerate / _astream).")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._calls_sink.setdefault(self.provider_id, []).append(list(messages))
        self._kwargs_sink.setdefault(self.provider_id, []).append(dict(kwargs))
        if self.scenario.delay:
            await asyncio.sleep(self.scenario.delay)
        if self.scenario.exception is not None:
            raise self.scenario.exception
        text = self.scenario.text or ""
        message = AIMessage(content=text, usage_metadata=_to_usage_metadata(self.scenario.usage))
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        self._calls_sink.setdefault(self.provider_id, []).append(list(messages))
        self._kwargs_sink.setdefault(self.provider_id, []).append(dict(kwargs))
        if self.scenario.delay:
            await asyncio.sleep(self.scenario.delay)
        if self.scenario.exception is not None:
            raise self.scenario.exception

        chunks = self.scenario.chunks
        if chunks is None:
            chunks = [self.scenario.text] if self.scenario.text else []

        usage_metadata = _to_usage_metadata(self.scenario.usage)
        last_idx = len(chunks) - 1
        for i, piece in enumerate(chunks):
            # Attach usage_metadata to the final chunk so collectors that
            # accumulate per-chunk usage (e.g. RobustChain via StreamExecutor)
            # see the totals — mirrors how Anthropic / OpenAI SDKs report usage.
            attach: UsageMetadata | None = (
                cast(UsageMetadata, usage_metadata) if i == last_idx else None
            )
            message = AIMessageChunk(content=piece, usage_metadata=attach)
            yield ChatGenerationChunk(message=message)

        if self.scenario.chunks_exception is not None:
            raise self.scenario.chunks_exception


def _to_usage_metadata(usage: dict[str, int] | None) -> dict[str, int] | None:
    if usage is None:
        return None
    # LangChain expects "input_tokens" / "output_tokens" / "total_tokens".
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get(
            "total_tokens",
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        ),
    }
