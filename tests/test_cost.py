"""Unit tests for ``robust_llm_chain.cost``.

Pure-function module — no ``RobustChain`` instance needed.
"""

from robust_llm_chain.cost import compute_cost
from robust_llm_chain.types import ModelSpec, PricingSpec, TokenUsage


def test_compute_cost_returns_none_when_pricing_unset():
    """No pricing attached → cost tracking is opt-in (returns None)."""
    spec = ModelSpec(model_id="m", pricing=None)
    cost = compute_cost(spec, TokenUsage(input_tokens=100, output_tokens=200))
    assert cost is None


def test_compute_cost_basic_input_output_only():
    """1M input @ $1 + 1M output @ $4 = $5 total."""
    spec = ModelSpec(
        model_id="m",
        pricing=PricingSpec(input_per_1m=1.0, output_per_1m=4.0),
    )
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000)
    cost = compute_cost(spec, usage)
    assert cost is not None
    assert cost.input_cost == 1.0
    assert cost.output_cost == 4.0
    assert cost.total_cost == 5.0
    assert cost.currency == "USD"


def test_compute_cost_cache_rate_defaults_when_unset():
    """Cache read defaults to input_per_1m * 0.1, write to * 1.25."""
    spec = ModelSpec(
        model_id="m",
        pricing=PricingSpec(input_per_1m=10.0, output_per_1m=40.0),  # cache rates unset
    )
    usage = TokenUsage(cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
    cost = compute_cost(spec, usage)
    assert cost is not None
    assert cost.cache_read_cost == 1.0  # 10 * 0.1
    assert cost.cache_write_cost == 12.5  # 10 * 1.25


def test_compute_cost_explicit_cache_rates_used_when_set():
    """Explicit cache rates override the input_per_1m-based defaults."""
    spec = ModelSpec(
        model_id="m",
        pricing=PricingSpec(
            input_per_1m=10.0,
            output_per_1m=40.0,
            cache_read_per_1m=2.0,
            cache_write_per_1m=20.0,
        ),
    )
    usage = TokenUsage(cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
    cost = compute_cost(spec, usage)
    assert cost is not None
    assert cost.cache_read_cost == 2.0
    assert cost.cache_write_cost == 20.0


def test_compute_cost_currency_propagates_from_pricing():
    """``CostEstimate.currency`` mirrors ``PricingSpec.currency``."""
    spec = ModelSpec(
        model_id="m",
        pricing=PricingSpec(input_per_1m=1.0, output_per_1m=2.0, currency="EUR"),
    )
    cost = compute_cost(spec, TokenUsage(input_tokens=1, output_tokens=1))
    assert cost is not None
    assert cost.currency == "EUR"
