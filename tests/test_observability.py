"""Unit tests for ``robust_llm_chain.observability.langsmith``.

Phase 4 (T12). Verifies:
- silent no-op when ``LANGSMITH_API_KEY`` unset or ``run_id`` is None
- ``Client.update_run`` invoked via ``asyncio.to_thread`` (non-blocking)
- ``Semaphore(50)`` bounded backpressure: drops + WARN once when full
- 5-second cleanup timeout swallowed (does not block the caller)
"""

import asyncio
import logging
import sys
import time
from types import ModuleType

import pytest

from robust_llm_chain.observability import langsmith as ls


@pytest.fixture(autouse=True)
def _reset_langsmith_module():
    """Reset module-level state before/after each test."""
    ls.reset_for_tests()
    yield
    ls.reset_for_tests()


def _install_fake_langsmith(monkeypatch, captured: list[dict]) -> None:
    class _FakeClient:
        def update_run(self, run_id: str, **kwargs: object) -> None:
            captured.append({"run_id": run_id, **kwargs})

    fake = ModuleType("langsmith")
    fake.Client = _FakeClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake)


# ──────────────────────────────────────────────────────────────────────────────
# No-op paths
# ──────────────────────────────────────────────────────────────────────────────


def test_no_op_when_env_missing(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    captured: list[dict] = []
    _install_fake_langsmith(monkeypatch, captured)

    asyncio.run(ls.cleanup_run("any-run-id", RuntimeError("never seen")))
    assert captured == []


def test_no_op_when_run_id_is_none(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")
    captured: list[dict] = []
    _install_fake_langsmith(monkeypatch, captured)

    asyncio.run(ls.cleanup_run(None, None))
    assert captured == []


# ──────────────────────────────────────────────────────────────────────────────
# Happy path — Client.update_run dispatched via to_thread
# ──────────────────────────────────────────────────────────────────────────────


def test_update_run_called_with_run_id_and_error(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")
    captured: list[dict] = []
    _install_fake_langsmith(monkeypatch, captured)

    asyncio.run(ls.cleanup_run("abc-123", RuntimeError("oops")))

    assert len(captured) == 1
    record = captured[0]
    assert record["run_id"] == "abc-123"
    assert "error" in record
    assert "oops" in str(record["error"])
    assert "end_time" in record


def test_update_run_with_no_error_passes_none(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")
    captured: list[dict] = []
    _install_fake_langsmith(monkeypatch, captured)

    asyncio.run(ls.cleanup_run("abc", None))

    assert captured[0]["error"] is None


def test_cleanup_run_sanitizes_credential_in_error_before_sending(monkeypatch):
    """Raw error text containing credential patterns must be sanitized.

    Hardening: prevents provider SDK error messages (which sometimes echo the
    api_key back in 401/403 responses) from leaking to LangSmith via the
    cleanup_run path. ``sanitize_message`` masks known prefixes; without this,
    a ``LANGCHAIN_TRACING_V2=true`` user would see credentials show up in the
    LangSmith dashboard's run.error field.
    """
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")
    captured: list[dict] = []
    _install_fake_langsmith(monkeypatch, captured)

    leak_marker = "sk-ant-api03-leak-canary-do-not-send-1234567890"
    error = RuntimeError(f"401 Unauthorized: invalid api key '{leak_marker}'")
    asyncio.run(ls.cleanup_run("run-id", error))

    assert len(captured) == 1
    sent = str(captured[0]["error"])
    assert leak_marker not in sent, "raw credential leaked to LangSmith via cleanup_run"
    assert "***" in sent, "sanitize_message must mask credential patterns"


# ──────────────────────────────────────────────────────────────────────────────
# Backpressure — Semaphore(50) drops new work when locked
# ──────────────────────────────────────────────────────────────────────────────


def test_drops_silently_when_semaphore_locked_and_logs_warn_once(monkeypatch, caplog):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")
    captured: list[dict] = []
    _install_fake_langsmith(monkeypatch, captured)

    async def _run():
        sem = ls._get_semaphore()
        # Saturate the semaphore by acquiring all 50 slots.
        for _ in range(ls._MAX_INFLIGHT):
            await sem.acquire()
        try:
            with caplog.at_level(logging.WARNING, logger=ls.logger.name):
                await ls.cleanup_run("dropped-1", None)
                await ls.cleanup_run("dropped-2", None)
                await ls.cleanup_run("dropped-3", None)
            # No update_run call — all dropped.
            assert captured == []
            # WARN logged at most once (rate-limited drop notice).
            drop_records = [
                r
                for r in caplog.records
                if r.levelno == logging.WARNING
                and "drop" in (getattr(r, "event", "") or r.getMessage().lower())
            ]
            assert len(drop_records) == 1
        finally:
            for _ in range(ls._MAX_INFLIGHT):
                sem.release()

    asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Cleanup timeout — does not block the caller
# ──────────────────────────────────────────────────────────────────────────────


def test_cleanup_timeout_does_not_block_caller(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")

    async def _slow_update_run(run_id: str, error: BaseException | None) -> None:
        await asyncio.sleep(60)

    monkeypatch.setattr(ls, "_update_run", _slow_update_run)
    monkeypatch.setattr(ls, "_CLEANUP_TIMEOUT_SEC", 0.05)

    async def _run():
        start = time.monotonic()
        await ls.cleanup_run("slow", None)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"cleanup blocked too long: {elapsed:.2f}s"

    asyncio.run(_run())
