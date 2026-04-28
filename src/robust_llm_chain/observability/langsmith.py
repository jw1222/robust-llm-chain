"""LangSmith pending-run cleanup with semaphore-bounded backpressure.

Phase 4 (T12) implementation. The stub keeps the public function
importable. Activation is gated by ``LANGSMITH_API_KEY``; when unset the
function silently returns.
"""


async def cleanup_run(run_id: str | None, error: BaseException | None) -> None:
    """Mark a pending LangSmith run as ``error`` (best-effort, non-blocking).

    Phase 4 (T12) wires this to ``langsmith.Client.update_run`` via
    ``asyncio.to_thread`` and bounds concurrent in-flight calls with
    ``asyncio.Semaphore(50)``.

    Args:
        run_id: The LangSmith run id (``None`` when LangSmith is inactive).
        error: The exception that terminated the run, or ``None`` for
            successful completion.
    """
    raise NotImplementedError(
        "observability.langsmith.cleanup_run is implemented in Phase 4 (T12)."
    )
