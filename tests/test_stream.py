"""Unit tests for ``robust_llm_chain.stream.StreamExecutor``.

Phase 4 (T8). Three phases:
  Phase 1: ``first_token`` wait — bounded by ``first_token_timeout``.
  Phase 2: chunk pump — bounded cumulatively by ``per_provider_timeout``.
  Phase 3: ``aclose()`` cleanup — bounded by ``stream_cleanup_timeout``;
           failures here must not block the caller.

Tests use lightweight async-iterator mocks rather than ``FakeAdapter``
because we need fine-grained control over inter-chunk timing and
``aclose()`` behavior.
"""

import asyncio
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, BaseMessageChunk, HumanMessage

from robust_llm_chain.errors import ProviderTimeout
from robust_llm_chain.stream import StreamExecutor

# ──────────────────────────────────────────────────────────────────────────────
# Mock model — exposes only ``astream`` (duck typing; StreamExecutor doesn't
# care about the rest of BaseChatModel).
# ──────────────────────────────────────────────────────────────────────────────


class _GenModel:
    """Mock ``BaseChatModel`` whose ``astream`` returns a configured iterator."""

    def __init__(self, gen_factory):
        self._gen_factory = gen_factory
        self.last_aclose_called = False

    def astream(self, messages):
        return self._gen_factory(self)


def _chunk(text: str) -> BaseMessageChunk:
    return AIMessageChunk(content=text)


def _executor(*, first_token: float = 1.0, per_provider: float = 5.0, cleanup: float = 1.0):
    return StreamExecutor(
        first_token_timeout=first_token,
        per_provider_timeout=per_provider,
        stream_cleanup_timeout=cleanup,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 — first_token
# ──────────────────────────────────────────────────────────────────────────────


def test_first_token_within_timeout_yields_first_chunk():
    async def _gen(model):
        await asyncio.sleep(0.01)
        yield _chunk("alpha")

    async def _run():
        model = _GenModel(_gen)
        chunks = [c async for c in _executor(first_token=0.5).stream(model, [HumanMessage("hi")])]
        assert [c.content for c in chunks] == ["alpha"]

    asyncio.run(_run())


def test_first_token_timeout_raises_provider_timeout():
    async def _gen(model):
        await asyncio.sleep(0.5)
        yield _chunk("late")

    async def _run():
        model = _GenModel(_gen)
        try:
            async for _ in _executor(first_token=0.05).stream(model, [HumanMessage("hi")]):
                raise AssertionError("should have timed out before first chunk")
        except ProviderTimeout as e:
            assert e.phase == "first_token"
            return
        raise AssertionError("expected ProviderTimeout")

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — chunk pump
# ──────────────────────────────────────────────────────────────────────────────


def test_collects_all_chunks_in_order():
    async def _gen(model):
        for s in ("a", "b", "c"):
            yield _chunk(s)

    async def _run():
        model = _GenModel(_gen)
        chunks = [c async for c in _executor().stream(model, [HumanMessage("hi")])]
        assert [c.content for c in chunks] == ["a", "b", "c"]

    asyncio.run(_run())


def test_per_provider_timeout_during_chunks_raises_stream_phase():
    async def _gen(model):
        yield _chunk("first")
        await asyncio.sleep(0.5)  # exceeds per_provider budget
        yield _chunk("never")

    async def _run():
        model = _GenModel(_gen)
        seen: list[str] = []
        try:
            async for c in _executor(first_token=1.0, per_provider=0.05).stream(
                model, [HumanMessage("hi")]
            ):
                seen.append(str(c.content))
        except ProviderTimeout as e:
            assert e.phase == "stream"
            assert seen == ["first"]
            return
        raise AssertionError("expected ProviderTimeout(phase='stream')")

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 — aclose cleanup
# ──────────────────────────────────────────────────────────────────────────────


class _RecordingIterator:
    """Async iterator that records whether aclose() was awaited."""

    def __init__(self, items: list[BaseMessageChunk], aclose_blocks: bool = False):
        self._items = items
        self._idx = 0
        self.aclose_called = False
        self._aclose_blocks = aclose_blocks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._idx]
        self._idx += 1
        return item

    async def aclose(self):
        self.aclose_called = True
        if self._aclose_blocks:
            await asyncio.sleep(60)  # simulate hang


def test_cleanup_aclose_invoked_after_normal_completion():
    rec = _RecordingIterator([_chunk("only")])

    class _M:
        def astream(self, messages):
            return rec

    async def _run():
        model = _M()
        chunks = [c async for c in _executor().stream(model, [HumanMessage("hi")])]
        assert [c.content for c in chunks] == ["only"]
        assert rec.aclose_called is True

    asyncio.run(_run())


def test_cleanup_timeout_does_not_block_caller():
    rec = _RecordingIterator([_chunk("only")], aclose_blocks=True)

    class _M:
        def astream(self, messages):
            return rec

    async def _run():
        model = _M()
        # cleanup=0.05 forces wait_for to bail; the async generator must still
        # exit cleanly without re-raising.
        loop_start = asyncio.get_event_loop().time()
        chunks = [c async for c in _executor(cleanup=0.05).stream(model, [HumanMessage("hi")])]
        elapsed = asyncio.get_event_loop().time() - loop_start
        assert [c.content for c in chunks] == ["only"]
        assert rec.aclose_called is True
        assert elapsed < 1.0, f"cleanup blocked main too long: {elapsed:.2f}s"

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# collect() — ainvoke path
# ──────────────────────────────────────────────────────────────────────────────


def test_collect_combines_chunks_and_usage_metadata():
    async def _gen(model):
        yield AIMessageChunk(
            content="hello ",
            usage_metadata={"input_tokens": 4, "output_tokens": 0, "total_tokens": 4},
        )
        yield AIMessageChunk(
            content="world",
            usage_metadata={"input_tokens": 0, "output_tokens": 6, "total_tokens": 6},
        )

    async def _run():
        model = _GenModel(_gen)
        message, usage = await _executor().collect(model, [HumanMessage("hi")])
        assert message.content == "hello world"
        assert usage.input_tokens == 4
        assert usage.output_tokens == 6
        assert usage.total_tokens == 10

    asyncio.run(_run())


def test_collect_returns_empty_message_when_no_chunks():
    async def _gen(model):
        if False:
            yield  # empty generator

    async def _run():
        model = _GenModel(_gen)
        message, usage = await _executor().collect(model, [HumanMessage("hi")])
        assert message.content == ""
        assert usage.total_tokens == 0

    asyncio.run(_run())


# Confirm AsyncIterator typing — sanity check that stream() really is one.


def test_stream_returns_async_iterator():
    async def _gen(model):
        yield _chunk("x")

    async def _run():
        model = _GenModel(_gen)
        gen = _executor().stream(model, [HumanMessage("hi")])
        assert isinstance(gen, AsyncIterator)

    asyncio.run(_run())
