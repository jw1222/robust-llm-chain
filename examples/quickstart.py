"""README quickstart, exact copy.

Run with:
    uv run python examples/quickstart.py

Requires both ``ANTHROPIC_API_KEY`` and ``OPENROUTER_API_KEY`` in the
environment. Missing either → ``KeyError`` from the builder with the exact
env var name (fail-fast).

Why ``RobustChain.builder()``? It's the most concise way to express the
common pattern (multiple providers via env defaults) without the dict /
vendor-prefix collision that ``from_env(model_ids={...})`` can show, and
without the verbosity of constructing ``ProviderSpec`` instances by hand.
For multi-key / multi-region / cross-vendor patterns, see
``examples/builder.py``. For the explicit-list path, see
``examples/advanced.py``.
"""

import asyncio
import sys

from robust_llm_chain import RobustChain
from robust_llm_chain.errors import NoProvidersConfigured


def main() -> None:
    chain = (
        RobustChain.builder()
        .add_anthropic(model="claude-haiku-4-5-20251001", priority=0)
        .add_openrouter(model="anthropic/claude-haiku-4.5", priority=1)
        .build()
    )
    # acall: convenience method that returns a ChainResult with operational metadata
    result = asyncio.run(chain.acall("두 줄로 자기소개 해줘."))
    print(result.output.content)
    print(f"used: {result.provider_used.id} | tokens: {result.usage}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as e:
        sys.stderr.write(
            f"Missing environment variable: {e}\n"
            "Set ANTHROPIC_API_KEY and OPENROUTER_API_KEY, or copy .env.example → .env.\n"
        )
        sys.exit(1)
    except NoProvidersConfigured as e:
        sys.stderr.write(f"NoProvidersConfigured: {e}\n")
        sys.exit(2)
