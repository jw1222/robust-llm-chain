"""LangSmith pending-run cleanup with semaphore-bounded backpressure.

Activated transparently when ``LANGSMITH_API_KEY`` is set in the environment.
When unset, ``cleanup_run`` returns silently. Concurrent in-flight cleanup
calls are bounded to ``_MAX_INFLIGHT`` (50) — when the bound is hit, the new
work is dropped silently and a single WARN log is emitted (rate-limited).
The cleanup itself is wrapped in a ``_CLEANUP_TIMEOUT_SEC`` (5s) timeout so
LangSmith hiccups never block the caller's hot path.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Final

logger = logging.getLogger(__name__)

#: Maximum concurrent in-flight cleanup tasks.
_MAX_INFLIGHT: Final[int] = 50
#: Per-cleanup wall-clock timeout.
_CLEANUP_TIMEOUT_SEC: Final[float] = 5.0

# Module-level state — created lazily so import does not bind to a loop.
_semaphore: asyncio.Semaphore | None = None
_drop_logged: bool = False


def _get_semaphore() -> asyncio.Semaphore:
    """Return (and lazily create) the bounded in-flight semaphore."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_INFLIGHT)
    return _semaphore


def reset_for_tests() -> None:
    """Test helper — reset module-level state (semaphore + drop flag)."""
    global _semaphore, _drop_logged
    _semaphore = None
    _drop_logged = False


async def cleanup_run(run_id: str | None, error: BaseException | None) -> None:
    """Mark a pending LangSmith run as ``error`` (best-effort, non-blocking).

    No-op when ``LANGSMITH_API_KEY`` is unset or ``run_id`` is ``None``.
    Drops silently (with a one-shot WARN log) if the in-flight semaphore is
    saturated. Cleanup itself is bounded by ``_CLEANUP_TIMEOUT_SEC``.
    """
    if run_id is None or not os.environ.get("LANGSMITH_API_KEY"):
        return

    sem = _get_semaphore()
    if sem.locked():
        _maybe_log_drop()
        return

    async with sem:
        try:
            await asyncio.wait_for(_update_run(run_id, error), timeout=_CLEANUP_TIMEOUT_SEC)
        except TimeoutError:
            logger.warning(
                "langsmith cleanup timed out",
                extra={"event": "langsmith_cleanup_timeout", "run_id": run_id},
            )
        except Exception as exc:
            logger.warning(
                "langsmith cleanup failed",
                extra={
                    "event": "langsmith_cleanup_fail",
                    "run_id": run_id,
                    "error_type": type(exc).__name__,
                },
            )


def _maybe_log_drop() -> None:
    """Emit a single WARN noting backpressure drops; subsequent calls silent."""
    global _drop_logged
    if _drop_logged:
        return
    _drop_logged = True
    logger.warning(
        "langsmith cleanup backpressure: dropping (semaphore=%d full)",
        _MAX_INFLIGHT,
        extra={"event": "langsmith_cleanup_drop", "max_inflight": _MAX_INFLIGHT},
    )


async def _update_run(run_id: str, error: BaseException | None) -> None:
    """Invoke ``Client.update_run`` on the threadpool (blocking SDK call)."""
    from langsmith import Client

    client = Client()
    error_text = str(error) if error is not None else None
    await asyncio.to_thread(
        client.update_run,
        run_id,
        end_time=datetime.now(UTC),
        error=error_text,
    )
