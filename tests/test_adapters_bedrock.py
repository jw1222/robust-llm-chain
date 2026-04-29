"""Unit tests for ``robust_llm_chain.adapters.bedrock.BedrockAdapter``.

Phase 4 (T6 후속) — Round 0 결정 변경 후 v0.1에 추가된 Bedrock 어댑터.
``langchain-aws`` 의 ``ChatBedrockConverse`` 사용. region 처리 +
multi-region failover 패턴 (east + west) 검증.
"""

import sys

from langchain_aws import ChatBedrockConverse

from robust_llm_chain.adapters.bedrock import BedrockAdapter
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ModelSpec, ProviderSpec


def _spec(
    *,
    region: str | None = "us-east-1",
    max_output_tokens: int | None = None,
    aws_access_key_id: str | None = "AKIATEST",
    aws_secret_access_key: str | None = "secret",
) -> ProviderSpec:
    return ProviderSpec(
        id="bedrock-east",
        type="bedrock",
        model=ModelSpec(
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
            max_output_tokens=max_output_tokens,
        ),
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Identity / shape
# ──────────────────────────────────────────────────────────────────────────────


def test_bedrock_adapter_type_constant():
    assert BedrockAdapter.type == "bedrock"


# ──────────────────────────────────────────────────────────────────────────────
# build()
# ──────────────────────────────────────────────────────────────────────────────


def test_build_returns_chat_bedrock_converse():
    chat = BedrockAdapter().build(_spec())
    assert isinstance(chat, ChatBedrockConverse)


def test_build_passes_model_id_unchanged():
    chat = BedrockAdapter().build(_spec())
    assert chat.model_id == "anthropic.claude-haiku-4-5-20251001-v1:0"


def test_build_passes_region():
    chat = BedrockAdapter().build(_spec(region="us-west-2"))
    assert chat.region_name == "us-west-2"


def test_build_passes_max_output_tokens():
    chat = BedrockAdapter().build(_spec(max_output_tokens=1024))
    assert chat.max_tokens == 1024


def test_build_defaults_max_tokens_when_unset():
    chat = BedrockAdapter().build(_spec(max_output_tokens=None))
    assert chat.max_tokens == 4096


def test_build_omits_credentials_when_spec_lacks_them(monkeypatch):
    """spec.aws_*=None → ChatBedrockConverse uses boto3 default credential chain."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFROMENV")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secretfromenv")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    chat = BedrockAdapter().build(_spec(aws_access_key_id=None, aws_secret_access_key=None))
    # boto3 will resolve credentials from env at call time; here we just
    # verify the constructor accepts the omission without error.
    assert isinstance(chat, ChatBedrockConverse)


def test_build_raises_provider_inactive_when_extras_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_aws", None)
    try:
        BedrockAdapter().build(_spec())
    except ProviderInactive as e:
        assert "bedrock" in str(e).lower()
    else:
        raise AssertionError("expected ProviderInactive when extras missing")


# ──────────────────────────────────────────────────────────────────────────────
# credentials_present() — all three env vars required
# ──────────────────────────────────────────────────────────────────────────────


def test_credentials_present_requires_all_three_env_vars():
    creds = BedrockAdapter().credentials_present(
        {
            "AWS_ACCESS_KEY_ID": "AKIA...",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_REGION": "us-east-1",
        }
    )
    assert creds == {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "secret",
        "region": "us-east-1",
    }


def test_credentials_absent_when_any_one_missing():
    base = {
        "AWS_ACCESS_KEY_ID": "AKIA",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "AWS_REGION": "us-east-1",
    }
    for missing in base:
        env = {k: v for k, v in base.items() if k != missing}
        assert BedrockAdapter().credentials_present(env) is None, (
            f"expected None when {missing} missing"
        )


def test_credentials_absent_returns_none_for_empty_env():
    assert BedrockAdapter().credentials_present({}) is None


# ──────────────────────────────────────────────────────────────────────────────
# Multi-region pattern — same type, different region for cross-region failover
# ──────────────────────────────────────────────────────────────────────────────


def test_multi_region_specs_yield_distinct_models():
    """east + west specs each produce a ChatBedrockConverse with its own region."""
    east = ProviderSpec(
        id="bedrock-east",
        type="bedrock",
        model=ModelSpec(model_id="anthropic.claude-haiku-4-5-20251001-v1:0"),
        region="us-east-1",
        aws_access_key_id="AKIA",
        aws_secret_access_key="secret",
    )
    west = ProviderSpec(
        id="bedrock-west",
        type="bedrock",
        model=ModelSpec(model_id="anthropic.claude-haiku-4-5-20251001-v1:0"),
        region="us-west-2",
        aws_access_key_id="AKIA",
        aws_secret_access_key="secret",
    )
    adapter = BedrockAdapter()
    chat_east = adapter.build(east)
    chat_west = adapter.build(west)
    assert chat_east.region_name == "us-east-1"
    assert chat_west.region_name == "us-west-2"
