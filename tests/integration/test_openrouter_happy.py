"""Integration test — OpenRouter happy path.

Auto-skipped when ``OPENROUTER_API_KEY`` is not present.
"""

import asyncio
import os

import pytest

from robust_llm_chain import ModelSpec, ProviderSpec, RobustChain, TimeoutConfig


@pytest.mark.integration
@pytest.mark.openrouter
def test_openrouter_basic_call_returns_content():
    async def _run():
        chain = RobustChain(
            providers=[
                ProviderSpec(
                    id="openrouter",
                    type="openrouter",
                    api_key=os.environ["OPENROUTER_API_KEY"],
                    model=ModelSpec(
                        model_id="anthropic/claude-haiku-4.5",
                        max_output_tokens=20,
                    ),
                )
            ],
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply with just the word OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.id == "openrouter"
        assert result.usage.output_tokens > 0

    asyncio.run(_run())


@pytest.mark.integration
@pytest.mark.openrouter
def test_openrouter_from_env_factory_works():
    async def _run():
        chain = RobustChain.from_env(
            model_ids={"openrouter": "anthropic/claude-haiku-4.5"},
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.type == "openrouter"

    asyncio.run(_run())
