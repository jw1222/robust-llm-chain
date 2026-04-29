"""Cost calculation helpers — USD estimate from token usage and pricing.

Pure-function module separated from ``chain.py`` (CODING_STYLE §1.1 — single
responsibility). The orchestrator (`RobustChain`) calls ``compute_cost`` after
each successful call to populate ``ChainResult.cost`` and accumulate
``RobustChain.total_cost``.

This is a developer-side **estimate**, not authoritative billing — pricing
values come from the user-supplied ``PricingSpec`` and may drift from provider
mid-call rate changes. Useful for development-time cost monitoring.

Cache rate defaults (when ``PricingSpec.cache_read_per_1m`` /
``cache_write_per_1m`` are unset): ``input_per_1m * 0.1`` (read) and
``input_per_1m * 1.25`` (write) — Anthropic-style approximation.
"""

from __future__ import annotations

from typing import Final

from robust_llm_chain.types import CostEstimate, ModelSpec, TokenUsage

#: Tokens-per-million scale factor for the per-1M USD pricing format.
_PER_MILLION: Final[float] = 1_000_000.0
#: Default cache-read multiplier of ``input_per_1m`` when unset.
_DEFAULT_CACHE_READ_MULTIPLIER: Final[float] = 0.1
#: Default cache-write multiplier of ``input_per_1m`` when unset.
_DEFAULT_CACHE_WRITE_MULTIPLIER: Final[float] = 1.25


def compute_cost(model_spec: ModelSpec, usage: TokenUsage) -> CostEstimate | None:
    """Compute USD cost from ``usage`` against ``model_spec.pricing``.

    Returns ``None`` when no pricing is attached (cost tracking opt-in).
    """
    pricing = model_spec.pricing
    if pricing is None:
        return None
    cache_read_rate = (
        pricing.cache_read_per_1m
        if pricing.cache_read_per_1m is not None
        else pricing.input_per_1m * _DEFAULT_CACHE_READ_MULTIPLIER
    )
    cache_write_rate = (
        pricing.cache_write_per_1m
        if pricing.cache_write_per_1m is not None
        else pricing.input_per_1m * _DEFAULT_CACHE_WRITE_MULTIPLIER
    )
    input_cost = usage.input_tokens * pricing.input_per_1m / _PER_MILLION
    output_cost = usage.output_tokens * pricing.output_per_1m / _PER_MILLION
    cache_read_cost = usage.cache_read_tokens * cache_read_rate / _PER_MILLION
    cache_write_cost = usage.cache_write_tokens * cache_write_rate / _PER_MILLION
    total = input_cost + output_cost + cache_read_cost + cache_write_cost
    return CostEstimate(
        input_cost=input_cost,
        output_cost=output_cost,
        cache_read_cost=cache_read_cost,
        cache_write_cost=cache_write_cost,
        total_cost=total,
        currency=pricing.currency,
    )


__all__ = ["compute_cost"]
