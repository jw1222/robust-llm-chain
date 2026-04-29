"""AWS Bedrock adapter — wraps ``langchain_aws.ChatBedrockConverse``.

Activated by ``pip install "robust-llm-chain[bedrock]"``. Bedrock hosts
multiple model families including Anthropic Claude, so this adapter is
also part of the Anthropic Direct ↔ Bedrock ↔ OpenRouter same-model
failover chain (CONCEPT.md §6 차별점 #3).

Region handling: ``ProviderSpec.region`` propagates to ``ChatBedrockConverse
(region_name=...)``. To do cross-region failover, register two providers with
distinct ``id`` + ``region`` (e.g. ``id="bedrock-east"`` /
``id="bedrock-west"``) — the resolver round-robins between them.

Credentials: ``ProviderSpec.aws_access_key_id`` / ``aws_secret_access_key``
override env. When both are ``None`` the underlying boto3 default credential
chain (env, IAM role, ``~/.aws/credentials``) applies.
"""

from collections.abc import Mapping
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from robust_llm_chain.adapters import DEFAULT_MAX_OUTPUT_TOKENS
from robust_llm_chain.errors import ProviderInactive
from robust_llm_chain.types import ProviderSpec


class BedrockAdapter:
    """Build ``ChatBedrockConverse`` instances from ``ProviderSpec``.

    Uses the Converse API (``ChatBedrockConverse``) over the legacy
    ``ChatBedrock`` because Converse is the unified interface across model
    families and supports modern Anthropic features (cache, tool use).
    """

    type: ClassVar[str] = "bedrock"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        """Construct ``ChatBedrockConverse`` from ``spec``.

        Raises:
            ProviderInactive: ``langchain_aws`` is not importable.
        """
        try:
            from langchain_aws import ChatBedrockConverse
        except ImportError as e:
            raise ProviderInactive(
                'bedrock adapter requires `pip install "robust-llm-chain[bedrock]"`'
            ) from e

        max_tokens = spec.model.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        # Build kwargs incrementally so unset credentials defer to boto3's
        # default credential chain (env / IAM role / ~/.aws/credentials).
        kwargs: dict[str, object] = {
            "model": spec.model.model_id,
            "max_tokens": max_tokens,
        }
        if spec.region is not None:
            kwargs["region_name"] = spec.region
        if spec.aws_access_key_id is not None:
            kwargs["aws_access_key_id"] = SecretStr(spec.aws_access_key_id)
        if spec.aws_secret_access_key is not None:
            kwargs["aws_secret_access_key"] = SecretStr(spec.aws_secret_access_key)
        return ChatBedrockConverse(**kwargs)  # type: ignore[arg-type]

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        """Return credential dict if all three AWS env vars are set, else ``None``.

        Bedrock requires three pieces of information to authenticate:
        ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, ``AWS_REGION``.
        Missing any one → returns ``None`` so ``from_env`` skips this provider.
        """
        access_key = env.get("AWS_ACCESS_KEY_ID")
        secret_key = env.get("AWS_SECRET_ACCESS_KEY")
        region = env.get("AWS_REGION")
        if access_key is None or secret_key is None or region is None:
            return None
        return {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region": region,
        }
