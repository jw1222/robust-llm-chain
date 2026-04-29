"""Integration test — OpenAI Direct happy path.

Auto-skipped when ``OPENAI_API_KEY`` is not present.
"""

import asyncio
import os

import pytest

from robust_llm_chain import ModelSpec, ProviderSpec, RobustChain, TimeoutConfig


@pytest.mark.integration
@pytest.mark.openai
def test_openai_basic_call_returns_content():
    async def _run():
        chain = RobustChain(
            providers=[
                ProviderSpec(
                    id="openai-direct",
                    type="openai",
                    api_key=os.environ["OPENAI_API_KEY"],
                    model=ModelSpec(model_id="gpt-4o-mini", max_output_tokens=20),
                )
            ],
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply with just the word OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.id == "openai-direct"
        assert result.usage.output_tokens > 0

    asyncio.run(_run())


@pytest.mark.integration
@pytest.mark.openai
def test_openai_from_env_factory_works():
    async def _run():
        chain = RobustChain.from_env(
            model_ids={"openai": "gpt-4o-mini"},
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.type == "openai"

    asyncio.run(_run())
