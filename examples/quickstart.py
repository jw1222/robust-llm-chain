"""README quickstart, exact copy.

Run with:
    uv run python examples/quickstart.py

Requires both ``ANTHROPIC_API_KEY`` and ``OPENROUTER_API_KEY`` in the
environment. With either missing, the library raises
``NoProvidersConfigured`` immediately so you get a clear error.

Why explicit ``ProviderSpec`` (not ``from_env``)?
    The ``model_ids`` dict in ``from_env`` collides visually when an
    OpenRouter model id starts with ``anthropic/...`` (the dict key
    "anthropic" and the value's vendor prefix look the same). Explicit
    ``ProviderSpec`` separates ``id`` (your label), ``type`` (adapter), and
    ``model.model_id`` (the vendor's identifier) so each role is unambiguous.
    ``from_env`` is still available — see the README "Shortcut" callout.

For multi-key / multi-region / cross-vendor patterns (anything beyond "one
provider per type"), see ``examples/advanced.py``.
"""

import asyncio
import os
import sys

from robust_llm_chain import ModelSpec, ProviderSpec, RobustChain
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

    chain = RobustChain(
        providers=[
            ProviderSpec(
                id="anthropic-direct",
                type="anthropic",
                model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
                api_key=os.environ["ANTHROPIC_API_KEY"],
                priority=0,  # primary
            ),
            ProviderSpec(
                id="openrouter-claude",
                type="openrouter",
                model=ModelSpec(model_id="anthropic/claude-haiku-4.5"),
                api_key=os.environ["OPENROUTER_API_KEY"],
                priority=1,  # fallback when primary throttles
            ),
        ]
    )
    # acall: convenience method that returns a ChainResult with operational metadata
    result = asyncio.run(chain.acall("두 줄로 자기소개 해줘."))
    print(result.output.content)
    print(f"used: {result.provider_used.id} | tokens: {result.usage}")


if __name__ == "__main__":
    try:
        main()
    except NoProvidersConfigured as e:
        sys.stderr.write(f"NoProvidersConfigured: {e}\n")
        sys.exit(2)
