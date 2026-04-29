"""Fluent builder for ``RobustChain`` — a third configuration path.

The two existing paths (``RobustChain.from_env`` / explicit
``RobustChain(providers=[...])``) differ in *capability*: ``from_env`` is
dict-based and limited to one provider per type, the explicit list is
verbose but expresses everything. The builder collapses that split — every
pattern uses the same chained method shape:

    chain = (
        RobustChain.builder()
        .add_anthropic(model="claude-haiku-4-5-20251001")
        .add_anthropic(
            model="claude-haiku-4-5-20251001",
            env_var="ANTHROPIC_API_KEY_BACKUP",
            id="anthropic2",
        )
        .add_bedrock(model="anthropic.claude-haiku-4-5", region="us-east-1")
        .build()
    )

**Credentials**: pass ``api_key=...`` explicitly (overrides env), or rely on
the per-method default ``env_var`` (``ANTHROPIC_API_KEY`` etc.). If neither
the explicit value nor the env var is present, a ``KeyError`` is raised
immediately — fail-fast, opposite of ``from_env`` 's silent skip.

**Auto-id**: when ``id=`` is not given, the builder assigns
``"<type>-<N>"`` (e.g. ``"anthropic-1"``, ``"anthropic-2"``) so every spec
gets a unique label even with multi-key configurations.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Self

from robust_llm_chain.types import ModelSpec, ProviderSpec

if TYPE_CHECKING:
    from robust_llm_chain.chain import RobustChain


class RobustChainBuilder:
    """Collect ``ProviderSpec``s by chained ``add_*`` calls, then ``.build()``."""

    def __init__(self) -> None:
        self._specs: list[ProviderSpec] = []
        self._counts: dict[str, int] = {}

    # ── id helpers ──────────────────────────────────────────────────────────

    def _next_id(self, type_: str) -> str:
        """Return ``"<type>-<N>"`` (e.g. ``"anthropic-1"``)."""
        self._counts[type_] = self._counts.get(type_, 0) + 1
        return f"{type_}-{self._counts[type_]}"

    @staticmethod
    def _resolve_required_env(env_var: str) -> str:
        """Read ``env_var`` from process env; raise ``KeyError`` if missing."""
        try:
            return os.environ[env_var]
        except KeyError as exc:
            raise KeyError(
                f"{env_var} is not set in the environment. "
                f"Either set the env var or pass the value explicitly."
            ) from exc

    @classmethod
    def _resolve_api_key(cls, env_var: str, api_key: str | None) -> str:
        """Explicit ``api_key`` wins; otherwise read ``env_var``."""
        if api_key is not None:
            return api_key
        return cls._resolve_required_env(env_var)

    # ── add_* methods ───────────────────────────────────────────────────────

    def add_anthropic(
        self,
        *,
        model: str,
        env_var: str = "ANTHROPIC_API_KEY",
        api_key: str | None = None,
        id: str | None = None,
        priority: int = 0,
    ) -> Self:
        """Add an Anthropic Direct provider."""
        resolved_key = self._resolve_api_key(env_var, api_key)
        self._specs.append(
            ProviderSpec(
                id=id or self._next_id("anthropic"),
                type="anthropic",
                model=ModelSpec(model_id=model),
                api_key=resolved_key,
                priority=priority,
            )
        )
        return self

    def add_openrouter(
        self,
        *,
        model: str,
        env_var: str = "OPENROUTER_API_KEY",
        api_key: str | None = None,
        id: str | None = None,
        priority: int = 0,
    ) -> Self:
        """Add an OpenRouter provider."""
        resolved_key = self._resolve_api_key(env_var, api_key)
        self._specs.append(
            ProviderSpec(
                id=id or self._next_id("openrouter"),
                type="openrouter",
                model=ModelSpec(model_id=model),
                api_key=resolved_key,
                priority=priority,
            )
        )
        return self

    def add_openai(
        self,
        *,
        model: str,
        env_var: str = "OPENAI_API_KEY",
        api_key: str | None = None,
        id: str | None = None,
        priority: int = 0,
    ) -> Self:
        """Add an OpenAI Direct provider."""
        resolved_key = self._resolve_api_key(env_var, api_key)
        self._specs.append(
            ProviderSpec(
                id=id or self._next_id("openai"),
                type="openai",
                model=ModelSpec(model_id=model),
                api_key=resolved_key,
                priority=priority,
            )
        )
        return self

    def add_bedrock(
        self,
        *,
        model: str,
        region: str,
        aws_access_key_env: str = "AWS_ACCESS_KEY_ID",
        aws_secret_env: str = "AWS_SECRET_ACCESS_KEY",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        id: str | None = None,
        priority: int = 0,
    ) -> Self:
        """Add an AWS Bedrock provider.

        Unlike single-key providers, Bedrock has **three** required pieces:
        access key id, secret access key, and region. The region must be
        passed explicitly (no env default) so multi-region configurations
        are unambiguous.
        """
        ak = (
            aws_access_key_id
            if aws_access_key_id is not None
            else self._resolve_required_env(aws_access_key_env)
        )
        sk = (
            aws_secret_access_key
            if aws_secret_access_key is not None
            else self._resolve_required_env(aws_secret_env)
        )
        self._specs.append(
            ProviderSpec(
                id=id or self._next_id("bedrock"),
                type="bedrock",
                model=ModelSpec(model_id=model),
                aws_access_key_id=ak,
                aws_secret_access_key=sk,
                region=region,
                priority=priority,
            )
        )
        return self

    # ── terminal ────────────────────────────────────────────────────────────

    def build(self, **kwargs: Any) -> RobustChain:
        """Construct the ``RobustChain``. ``kwargs`` forward to ``RobustChain.__init__``.

        Raises ``NoProvidersConfigured`` (via ``RobustChain.__init__``) when
        no ``add_*`` was called.
        """
        from robust_llm_chain.chain import RobustChain

        return RobustChain(providers=self._specs, **kwargs)


__all__ = ["RobustChainBuilder"]
