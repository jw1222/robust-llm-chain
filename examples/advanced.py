"""Advanced patterns — multi-key / multi-region / cross-vendor failover.

The 30-second quickstart (``examples/quickstart.py``) uses ``from_env`` which
takes one provider per type (the ``model_ids`` dict has unique keys). Real
production setups often want more — these patterns require building the
``ProviderSpec`` list explicitly and passing it to ``RobustChain(providers=[...])``.

Run a single example:
    uv run python examples/advanced.py multikey
    uv run python examples/advanced.py 3way
    uv run python examples/advanced.py xvendor
    uv run python examples/advanced.py multiregion
"""

import asyncio
import os
import sys

from robust_llm_chain import ModelSpec, ProviderSpec, RobustChain
from robust_llm_chain.errors import NoProvidersConfigured


def _require(env_vars: list[str]) -> None:
    missing = [v for v in env_vars if not os.environ.get(v)]
    if missing:
        sys.stderr.write(f"Missing env: {', '.join(missing)}\n")
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 1 — Multi-key on the same provider (rate-limit headroom)
# ──────────────────────────────────────────────────────────────────────────────


def multikey() -> None:
    """Two Anthropic keys for double the rate limit.

    Same ``type``, distinct ``id``, equal ``priority`` → round-robin between
    the two keys. The backend (Local or Memcached) coordinates which call
    goes to which key.

    Required env: ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_BACKUP
    """
    _require(["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_BACKUP"])

    providers = [
        ProviderSpec(
            id="anthropic1",
            type="anthropic",
            model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
            api_key=os.environ["ANTHROPIC_API_KEY"],
            priority=0,
        ),
        ProviderSpec(
            id="anthropic2",
            type="anthropic",
            model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
            api_key=os.environ["ANTHROPIC_API_KEY_BACKUP"],
            priority=0,  # equal priority → round-robin between the two keys
        ),
    ]
    chain = RobustChain(providers=providers)
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | tokens: {result.usage}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 2 — 3-way Claude across Anthropic / Bedrock / OpenRouter
# ──────────────────────────────────────────────────────────────────────────────


def three_way_claude() -> None:
    """Strongest Claude failover — three independent paths to the same model.

    Priority ladder: try Anthropic Direct first (cheapest, highest quality);
    on 529/throttle fall back to Bedrock (different infra); finally OpenRouter
    (broadest reach). One model_id family, three vendor paths.

    Required env: ANTHROPIC_API_KEY, AWS_*, OPENROUTER_API_KEY
    """
    _require(
        [
            "ANTHROPIC_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "OPENROUTER_API_KEY",
        ]
    )

    providers = [
        ProviderSpec(
            id="anthropic-direct",
            type="anthropic",
            model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
            api_key=os.environ["ANTHROPIC_API_KEY"],
            priority=0,  # primary
        ),
        ProviderSpec(
            id="bedrock-east",
            type="bedrock",
            model=ModelSpec(model_id="anthropic.claude-haiku-4-5"),
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            region="us-east-1",
            priority=1,  # secondary — different infra
        ),
        ProviderSpec(
            id="openrouter-claude",
            type="openrouter",
            model=ModelSpec(model_id="anthropic/claude-haiku-4.5"),
            api_key=os.environ["OPENROUTER_API_KEY"],
            priority=2,  # tertiary
        ),
    ]
    chain = RobustChain(providers=providers)
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | model: {result.model_used.model_id}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 3 — Cross-vendor cross-model (Claude → GPT)
# ──────────────────────────────────────────────────────────────────────────────


def cross_vendor() -> None:
    """When Claude is unavailable, fall back to GPT — different model family.

    Useful when the primary vendor has a region-wide outage. Quality may
    differ between Claude and GPT for your prompt — measure before relying
    on this for production critical paths.

    Required env: ANTHROPIC_API_KEY, OPENAI_API_KEY
    """
    _require(["ANTHROPIC_API_KEY", "OPENAI_API_KEY"])

    providers = [
        ProviderSpec(
            id="claude",
            type="anthropic",
            model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
            api_key=os.environ["ANTHROPIC_API_KEY"],
            priority=0,
        ),
        ProviderSpec(
            id="gpt",
            type="openai",
            model=ModelSpec(model_id="gpt-4o-mini"),
            api_key=os.environ["OPENAI_API_KEY"],
            priority=1,  # cross-vendor cross-model fallback
        ),
    ]
    chain = RobustChain(providers=providers)
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | model: {result.model_used.model_id}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 4 — Bedrock multi-region (east + west)
# ──────────────────────────────────────────────────────────────────────────────


def multiregion() -> None:
    """Bedrock east → west failover for region-level resilience.

    Same Bedrock account, two regions. AWS regional outages are rare but
    real; this pattern keeps you serving across them.

    Required env: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    """
    _require(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])

    providers = [
        ProviderSpec(
            id="bedrock-east",
            type="bedrock",
            model=ModelSpec(model_id="anthropic.claude-haiku-4-5"),
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            region="us-east-1",
            priority=0,
        ),
        ProviderSpec(
            id="bedrock-west",
            type="bedrock",
            model=ModelSpec(model_id="anthropic.claude-haiku-4-5"),
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            region="us-west-2",
            priority=1,
        ),
    ]
    chain = RobustChain(providers=providers)
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | region: {result.provider_used.region}")


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────────────


_EXAMPLES = {
    "multikey": multikey,
    "3way": three_way_claude,
    "xvendor": cross_vendor,
    "multiregion": multiregion,
}


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in _EXAMPLES:
        sys.stderr.write(
            "usage: python examples/advanced.py [multikey | 3way | xvendor | multiregion]\n"
        )
        sys.exit(1)
    try:
        _EXAMPLES[sys.argv[1]]()
    except NoProvidersConfigured as e:
        sys.stderr.write(f"NoProvidersConfigured: {e}\n")
        sys.exit(2)
