"""Integration test — Anthropic Direct happy path.

Auto-skipped when ``ANTHROPIC_API_KEY`` is not present in the environment
(see ``tests/conftest.py`` :func:`pytest_collection_modifyitems`).

Run manually:
    uv run pytest tests/integration -m "integration and anthropic" -v

Cost discipline (CODING_STYLE §10.6):
- ``max_output_tokens=20`` — minimal token spend
- short prompt
- ``first_token`` timeout 15s (default), no library retry
"""

import asyncio
import os

import pytest

from robust_llm_chain import ModelSpec, ProviderSpec, RobustChain, TimeoutConfig


@pytest.mark.integration
@pytest.mark.anthropic
def test_anthropic_basic_call_returns_content():
    async def _run():
        chain = RobustChain(
            providers=[
                ProviderSpec(
                    id="anthropic-direct",
                    type="anthropic",
                    api_key=os.environ["ANTHROPIC_API_KEY"],
                    model=ModelSpec(
                        model_id="claude-haiku-4-5-20251001",
                        max_output_tokens=20,
                    ),
                )
            ],
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply with just the word OK", max_tokens=20)
        # Don't assert on content — LLM responses are non-deterministic.
        # Verify shape only.
        assert result.output.content
        assert result.provider_used.id == "anthropic-direct"
        assert result.usage.output_tokens > 0

    asyncio.run(_run())


@pytest.mark.integration
@pytest.mark.anthropic
def test_anthropic_from_env_factory_works():
    async def _run():
        chain = RobustChain.from_env(
            model_ids={"anthropic": "claude-haiku-4-5-20251001"},
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.type == "anthropic"

    asyncio.run(_run())
