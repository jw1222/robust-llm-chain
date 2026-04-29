"""Integration test — AWS Bedrock happy path (Anthropic Claude through Bedrock).

Auto-skipped when ``AWS_ACCESS_KEY_ID`` is not present (conftest also covers
``AWS_SECRET_ACCESS_KEY`` / ``AWS_REGION`` indirectly via the same marker —
the test itself will fail loudly if those are missing, prompting setup).
"""

import asyncio
import os

import pytest

from robust_llm_chain import ModelSpec, ProviderSpec, RobustChain, TimeoutConfig


@pytest.mark.integration
@pytest.mark.bedrock
def test_bedrock_anthropic_claude_basic_call():
    async def _run():
        chain = RobustChain(
            providers=[
                ProviderSpec(
                    id="bedrock-east",
                    type="bedrock",
                    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                    region=os.environ.get("AWS_REGION", "us-east-1"),
                    model=ModelSpec(
                        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                        max_output_tokens=20,
                    ),
                )
            ],
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply with just the word OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.id == "bedrock-east"
        assert result.usage.output_tokens > 0

    asyncio.run(_run())


@pytest.mark.integration
@pytest.mark.bedrock
def test_bedrock_from_env_factory_works():
    async def _run():
        chain = RobustChain.from_env(
            model_ids={"bedrock": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
            timeouts=TimeoutConfig(per_provider=30.0, first_token=15.0),
        )
        result = await chain.acall("Reply OK", max_tokens=20)
        assert result.output.content
        assert result.provider_used.type == "bedrock"

    asyncio.run(_run())
