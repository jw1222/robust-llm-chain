"""robust-llm-chain — Production-grade cross-vendor failover for LLM APIs.

Public API surface — only the symbols listed in ``__all__`` are part of the
versioned contract. Anything imported via subpaths (``robust_llm_chain.errors``,
``robust_llm_chain.backends``, ``robust_llm_chain.testing``) is also public,
but the package root re-exports the day-to-day essentials.
"""

from robust_llm_chain.builder import RobustChainBuilder, SingleKeyProviderType
from robust_llm_chain.chain import RobustChain
from robust_llm_chain.types import (
    AttemptRecord,
    ChainResult,
    CostEstimate,
    ModelSpec,
    PricingSpec,
    ProviderSpec,
    RobustChainInput,
    TimeoutConfig,
    TokenUsage,
)

__version__ = "0.3.0"

__all__ = [
    "AttemptRecord",
    "ChainResult",
    "CostEstimate",
    "ModelSpec",
    "PricingSpec",
    "ProviderSpec",
    "RobustChain",
    "RobustChainBuilder",
    "RobustChainInput",
    "SingleKeyProviderType",
    "TimeoutConfig",
    "TokenUsage",
    "__version__",
]
