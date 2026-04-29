"""Builder patterns — 4 production scenarios via ``RobustChain.builder()``.

This is the canonical reference for ``RobustChain.builder()`` (the recommended
configuration path — fluent, multi-key OK, credentials passed as values). For
the explicit ``providers=[ProviderSpec(...)]`` path, see the inline code
blocks in the README "Advanced usage" section.

The builder collapses the dict-vs-list semantic split: every pattern (single,
multi-key, multi-region, cross-vendor) uses the same chained shape via two
methods — ``add_provider(type=…)`` for single-key providers (Anthropic /
OpenAI / OpenRouter), and ``add_bedrock(...)`` for the asymmetric Bedrock
case (region + two credentials).

**Credentials are passed as values** — ``api_key=os.environ["..."]`` here, but
equally ``api_key=vault.get(...)`` from a secrets manager. The builder does
not read env vars on your behalf.

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


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 1 — Multi-key on the same provider
# ──────────────────────────────────────────────────────────────────────────────


def multikey() -> None:
    """Two Anthropic keys for double the rate limit.

    The pattern is **provider-agnostic** — the same shape works for every
    single-key provider by swapping ``type=`` and the env var prefix:

    - Anthropic: ``ANTHROPIC_API_KEY_1`` / ``ANTHROPIC_API_KEY_2``
    - OpenAI:    ``OPENAI_API_KEY_1`` / ``OPENAI_API_KEY_2``
    - OpenRouter:``OPENROUTER_API_KEY_1`` / ``OPENROUTER_API_KEY_2``
    - Bedrock:   per-region credential pairs (see ``multiregion`` below)

    Naming convention is your call (``_1``/``_2``, ``_PRIMARY``/``_BACKUP``,
    ``_TEAM_A``/``_TEAM_B`` — whatever your secret store uses); the builder
    only cares about the value you pass via ``api_key=``.

    Required env: ``ANTHROPIC_API_KEY_1``, ``ANTHROPIC_API_KEY_2``
    """
    _require(["ANTHROPIC_API_KEY_1", "ANTHROPIC_API_KEY_2"])

    chain = (
        RobustChain.builder()
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY_1"],
            id="anthropic-1",
        )
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY_2"],
            id="anthropic-2",
        )
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | tokens: {result.usage}")
    print(f"reply: {str(result.output.content)[:100]}")


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
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            priority=0,
        )
        .add_bedrock(
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region="us-east-1",
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            priority=1,
        )
        .add_provider(
            type="openrouter",
            model="anthropic/claude-haiku-4.5",
            api_key=os.environ["OPENROUTER_API_KEY"],
            priority=2,
        )
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | model: {result.model_used.model_id}")
    print(f"reply: {str(result.output.content)[:100]}")


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
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            priority=0,
        )
        .add_provider(
            type="openai",
            model="gpt-4o-mini",
            api_key=os.environ["OPENAI_API_KEY"],
            priority=1,
        )
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | model: {result.model_used.model_id}")
    print(f"reply: {str(result.output.content)[:100]}")


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 4 — Bedrock multi-region (east + west)
# ──────────────────────────────────────────────────────────────────────────────


def multiregion() -> None:
    """Bedrock east → west failover for region-level resilience.

    AWS credentials are **region-agnostic** — one IAM user's access key works
    in every region, so a single ``AWS_ACCESS_KEY_ID`` /
    ``AWS_SECRET_ACCESS_KEY`` pair is all you need to defend against a
    region-level outage. That's the typical setup and what this example shows.

    For blast-radius isolation (separate IAM users per region, cross-account
    deployments, etc.) just read distinct env vars per region — same shape,
    different ``os.environ[...]`` keys (``AWS_ACCESS_KEY_ID_EAST`` /
    ``..._WEST``, ``_1``/``_2``, ``_PRIMARY``/``_BACKUP``, whatever your
    secret store uses). To skip env entirely, source the value from a
    secrets manager: ``aws_access_key_id=vault.get("aws/east/access_key_id")``.

    Required env: ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``
    """
    _require(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])

    chain = (
        RobustChain.builder()
        .add_bedrock(
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region="us-east-1",
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            id="bedrock-east",
            priority=0,
        )
        .add_bedrock(
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region="us-west-2",
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            id="bedrock-west",
            priority=1,
        )
        .build()
    )
    result = asyncio.run(chain.acall("두 줄로 자기소개."))
    print(f"used: {result.provider_used.id} | region: {result.provider_used.region}")
    print(f"reply: {str(result.output.content)[:100]}")


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
