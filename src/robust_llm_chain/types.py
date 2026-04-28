"""Public data model: type aliases and dataclasses.

All public dataclasses live here. ``frozen=True`` for value-like specs
(ProviderSpec, ModelSpec, PricingSpec, AttemptRecord, CostEstimate,
TimeoutConfig). ``ChainResult`` is mutable to support the astream
lifecycle (provisional → fallback append → first-token confirm →
final commit). ``TokenUsage`` is mutable to support ``__iadd__``
accumulation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from langchain_core.messages import BaseMessage
from langchain_core.prompt_values import PromptValue

# ──────────────────────────────────────────────────────────────────────────────
# Type aliases (public)
# ──────────────────────────────────────────────────────────────────────────────

# PEP 695 type alias (Python 3.12+). The right-hand side is lazily evaluated.
type RobustChainInput = str | PromptValue | list[BaseMessage]


# ──────────────────────────────────────────────────────────────────────────────
# Pricing / Model / Provider
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PricingSpec:
    """USD per 1M tokens. The user is responsible for keeping rates current."""

    input_per_1m: float
    output_per_1m: float
    cache_read_per_1m: float | None = None
    cache_write_per_1m: float | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class ModelSpec:
    """Model attributes. Orthogonal to provider."""

    model_id: str
    pricing: PricingSpec | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    deprecated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Authentication / connection info bundled with the model to use.

    Credential fields use ``repr=False`` and a custom ``__repr__`` to prevent
    accidental key exposure in logs. ``slots=True`` blocks ``vars(spec)``
    bypass.
    """

    id: str
    type: str
    model: ModelSpec
    api_key: str | None = field(default=None, repr=False)
    aws_access_key_id: str | None = field(default=None, repr=False)
    aws_secret_access_key: str | None = field(default=None, repr=False)
    region: str | None = None
    priority: int = 0

    def __repr__(self) -> str:
        return (
            f"ProviderSpec(id={self.id!r}, type={self.type!r}, "
            f"model={self.model!r}, region={self.region!r}, "
            f"priority={self.priority})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Token usage / Cost
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class TokenUsage:
    """Token counts. Mutable to support ``+=`` accumulation."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def __iadd__(self, other: "TokenUsage") -> "TokenUsage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.total_tokens += other.total_tokens
        return self


@dataclass(frozen=True)
class CostEstimate:
    """Computed cost from ``TokenUsage`` and ``PricingSpec``."""

    input_cost: float
    output_cost: float
    cache_read_cost: float
    cache_write_cost: float
    total_cost: float
    currency: str = "USD"


# ──────────────────────────────────────────────────────────────────────────────
# Timeout config
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimeoutConfig:
    """Timeout bundle. Reduces ``RobustChain.__init__`` argument count."""

    per_provider: float = 60.0
    first_token: float = 15.0
    total: float | None = None
    stream_cleanup: float = 2.0


# ──────────────────────────────────────────────────────────────────────────────
# Attempt / Result
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttemptRecord:
    """Single provider attempt record.

    ``error_message`` is sanitized via ``_security.sanitize_message`` at
    construction time by the orchestrator. Raw provider errors are not
    stored here.
    """

    provider_id: str
    provider_type: str
    model_id: str
    phase: Literal["model_creation", "first_token", "stream", "post_processing"]
    elapsed_ms: float
    error_type: str | None
    error_message: str | None
    fallback_eligible: bool
    run_id: UUID | None


@dataclass
class ChainResult:
    """End-to-end call result. Mutable for astream lifecycle stages.

    ``input`` and ``output`` are exposed so the user's own audit logger can
    persist prompt/response. The library itself never logs them.
    """

    input: list[BaseMessage]
    output: BaseMessage
    usage: TokenUsage
    cost: CostEstimate | None
    provider_used: ProviderSpec
    model_used: ModelSpec
    attempts: list[AttemptRecord]
    elapsed_ms: float
