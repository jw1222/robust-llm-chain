"""README 30-second quickstart, exact copy.

Run with:
    uv run python examples/quickstart.py

Requires both ``ANTHROPIC_API_KEY`` and ``OPENROUTER_API_KEY`` in the
environment. With either missing, the library raises
``NoProvidersConfigured`` immediately so you get a clear error.

For multi-key / multi-region / cross-vendor patterns (anything beyond "one
provider per type"), see ``examples/advanced.py``.
"""

import asyncio
import os
import sys

from robust_llm_chain import RobustChain
from robust_llm_chain.errors import NoProvidersConfigured


def _require_keys() -> None:
    missing = [
        name for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY") if not os.environ.get(name)
    ]
    if missing:
        joined = ", ".join(missing)
        sys.stderr.write(
            f"Missing environment variable(s): {joined}\n"
            "Set them and re-run, or copy .env.example → .env and fill in values.\n"
        )
        sys.exit(1)


def main() -> None:
    _require_keys()

    # provider type → that provider's model_id
    chain = RobustChain.from_env(
        model_ids={
            "anthropic": "claude-haiku-4-5-20251001",
            "openrouter": "anthropic/claude-haiku-4.5",
        }
    )
    # acall: convenience method that returns a ChainResult with operational metadata
    result = asyncio.run(chain.acall("두 줄로 자기소개 해줘."))
    print(result.output.content)
    print(result.provider_used.id, result.usage)


if __name__ == "__main__":
    try:
        main()
    except NoProvidersConfigured as e:
        sys.stderr.write(f"NoProvidersConfigured: {e}\n")
        sys.exit(2)
    except NotImplementedError as e:
        # Phase 3 stub — RobustChain.from_env is implemented in Phase 4 (T10).
        sys.stderr.write(f"This example requires Phase 4 implementation: {e}\n")
        sys.exit(3)
