"""Builder patterns — same 4 production scenarios as ``examples/advanced.py``,
expressed via ``RobustChain.builder()`` (the third configuration path).

The builder collapses the dict-vs-list semantic split: every pattern (single
provider, multi-key, multi-region, cross-vendor) uses the same chained
``add_*`` shape. It reads credentials from env vars by default (configurable
``env_var=`` per ``add_*``) and **fails fast** with a ``KeyError`` if a
credential is missing — opposite of ``from_env`` 's silent skip.

Run a single example:
    uv run python examples/builder.py multikey
    uv run python examples/builder.py 3way
    uv run python examples/builder.py xvendor
    uv run python examples/builder.py multiregion
"""

import asyncio
import os
import sys

from robust_llm_chain import RobustChain
from robust_llm_chain.errors import NoProvidersConfigured


def _require(env_vars: list[str]) -> None:
    missing = [v for v in env_vars if not os.environ.get(v)]
    if missing:
        sys.stderr.write(f"Missing env: {', '.join(missing)}\n")
        sys.exit(1)


def _content_to_str(content: object) -> str:
    """LangChain ``BaseMessage.content`` is ``str | list``; Bedrock often returns list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in content]
        return " ".join(parts)
    return str(content)


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 1 — Multi-key on the same provider
# ──────────────────────────────────────────────────────────────────────────────


def multikey() -> None:
    """Two Anthropic keys for double the rate limit.

    Required env: ``ANTHROPIC_API_KEY``, ``ANTHROPIC_API_KEY_BACKUP``
    """
    _require(["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_BACKUP"])

    chain = (
        RobustChain.builder()
        .add_anthropic(model="claude-haiku-4-5-20251001", id="anthropic-1")
        .add_anthropic(
            model="claude-haiku-4-5-20251001",
            env_var="ANTHROPIC_API_KEY_BACKUP",
            id="anthropic-2",
        )
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | tokens: {result.usage}")
    print(f"reply: {_content_to_str(result.output.content)[:100]}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 2 — 3-way Claude across Anthropic / Bedrock / OpenRouter
# ──────────────────────────────────────────────────────────────────────────────


def three_way_claude() -> None:
    """Strongest Claude failover — three independent paths to the same model.

    Required env: ``ANTHROPIC_API_KEY``, AWS creds, ``OPENROUTER_API_KEY``
    """
    _require(
        [
            "ANTHROPIC_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "OPENROUTER_API_KEY",
        ]
    )

    chain = (
        RobustChain.builder()
        .add_anthropic(model="claude-haiku-4-5-20251001", priority=0)
        .add_bedrock(
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region="us-east-1",
            priority=1,
        )
        .add_openrouter(model="anthropic/claude-haiku-4.5", priority=2)
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | model: {result.model_used.model_id}")
    print(f"reply: {_content_to_str(result.output.content)[:100]}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 3 — Cross-vendor cross-model (Claude → GPT)
# ──────────────────────────────────────────────────────────────────────────────


def cross_vendor() -> None:
    """When Claude is unavailable, fall back to GPT.

    Required env: ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``
    """
    _require(["ANTHROPIC_API_KEY", "OPENAI_API_KEY"])

    chain = (
        RobustChain.builder()
        .add_anthropic(model="claude-haiku-4-5-20251001", priority=0)
        .add_openai(model="gpt-4o-mini", priority=1)
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | model: {result.model_used.model_id}")
    print(f"reply: {_content_to_str(result.output.content)[:100]}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 4 — Bedrock multi-region (east + west)
# ──────────────────────────────────────────────────────────────────────────────


def multiregion() -> None:
    """Bedrock east → west failover for region-level resilience.

    Required env: ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``
    """
    _require(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])

    chain = (
        RobustChain.builder()
        .add_bedrock(
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region="us-east-1",
            id="bedrock-east",
            priority=0,
        )
        .add_bedrock(
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region="us-west-2",
            id="bedrock-west",
            priority=1,
        )
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | region: {result.provider_used.region}")
    print(f"reply: {_content_to_str(result.output.content)[:100]}")


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
            "usage: python examples/builder.py [multikey | 3way | xvendor | multiregion]\n"
        )
        sys.exit(1)
    try:
        _EXAMPLES[sys.argv[1]]()
    except NoProvidersConfigured as e:
        sys.stderr.write(f"NoProvidersConfigured: {e}\n")
        sys.exit(2)
