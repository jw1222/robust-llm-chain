"""README quickstart, exact copy.

Run with:
    uv run python examples/quickstart.py

Requires both ``ANTHROPIC_API_KEY`` and ``OPENROUTER_API_KEY`` in the
environment. The example reads them via ``os.environ[...]`` — missing →
``KeyError`` with the var name (Python's standard fail-fast).

Why ``RobustChain.builder()``? It's the most concise way to express the
common pattern (multiple providers) without the dict / vendor-prefix
collision that ``from_env(model_ids={...})`` can show, and without the
verbosity of constructing ``ProviderSpec`` instances by hand. For multi-key
/ multi-region / cross-vendor patterns, see ``examples/builder.py``. For
the explicit ``providers=[ProviderSpec(...)]`` path, see the inline code
blocks in the README "Advanced usage" section.
"""

import asyncio
import os
import sys

from robust_llm_chain import RobustChain
from robust_llm_chain.errors import NoProvidersConfigured


def main() -> None:
    chain = (
        RobustChain.builder()
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            priority=0,
        )
        .add_provider(
            type="openrouter",
            model="anthropic/claude-haiku-4.5",
            api_key=os.environ["OPENROUTER_API_KEY"],
            priority=1,
        )
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
