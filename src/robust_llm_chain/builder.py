"""Fluent builder for ``RobustChain`` — a third configuration path.

The two existing paths (``RobustChain.from_env`` / explicit
``RobustChain(providers=[...])``) differ in *capability*: ``from_env`` is
dict-based and limited to one provider per type, the explicit list is
verbose but expresses everything. The builder collapses that split — every
pattern (single, multi-key, multi-region, mixed) uses the same chained
method shape:

    chain = (
        RobustChain.builder()
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY_1"],
        )
        .add_provider(
            type="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key=os.environ["ANTHROPIC_API_KEY_2"],
        )
        .add_bedrock(
            model="anthropic.claude-haiku-4-5",
            region="us-east-1",
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        .build()
    )

**Credentials are passed as values, not env names.** Where the value comes
from — env var, secrets manager, Vault, a literal for tests — is the
caller's concern. The builder doesn't read env vars on your behalf. This
keeps the API single-purpose (assemble specs) and avoids the ambiguous
``env_var=`` kwarg that mixed *source* with *value*.

**Auto-id**: when ``id=`` is not given, the builder assigns
``"<type>-<N>"`` (e.g. ``"anthropic-1"``, ``"anthropic-2"``) so every spec
gets a unique label even with multi-key configurations.

**Two methods, not N**:

- ``add_provider(type=…)`` — single-key providers (Anthropic / OpenAI /
  OpenRouter). The signature is identical across types; only the ``type``
  literal changes.
- ``add_bedrock(...)`` — Bedrock has a different shape (region + two
  credentials), so it gets its own method instead of polluting
  ``add_provider`` with kwargs that are dead weight for everyone else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Self

from robust_llm_chain.types import ModelSpec, ProviderSpec

if TYPE_CHECKING:
    from robust_llm_chain.chain import RobustChain


SingleKeyProviderType = Literal["anthropic", "openai", "openrouter"]
"""Providers whose only credential is a single ``api_key`` string."""


class RobustChainBuilder:
    """Collect ``ProviderSpec`` s by chained ``add_*`` calls, then ``.build()``."""

    def __init__(self) -> None:
        self._specs: list[ProviderSpec] = []
        self._counts: dict[str, int] = {}

    def _next_id(self, type_: str) -> str:
        """Return ``"<type>-<N>"`` (e.g. ``"anthropic-1"``)."""
        self._counts[type_] = self._counts.get(type_, 0) + 1
        return f"{type_}-{self._counts[type_]}"

    # ── add methods ─────────────────────────────────────────────────────────

    def add_provider(
        self,
        *,
        type: SingleKeyProviderType,
        model: str,
        api_key: str,
        id: str | None = None,
        priority: int = 0,
    ) -> Self:
        """Add a single-key provider (Anthropic / OpenAI / OpenRouter).

        For Bedrock (region + two credentials) use :meth:`add_bedrock` instead.
        """
        self._specs.append(
            ProviderSpec(
                id=id or self._next_id(type),
                type=type,
                model=ModelSpec(model_id=model),
                api_key=api_key,
                priority=priority,
            )
        )
        return self

    def add_bedrock(
        self,
        *,
        model: str,
        region: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        id: str | None = None,
        priority: int = 0,
    ) -> Self:
        """Add an AWS Bedrock provider.

        Unlike single-key providers, Bedrock has *three* required pieces:
        access key id, secret access key, and region. All three are passed
        as values — read them from env / Secrets Manager / Vault yourself.
        """
        self._specs.append(
            ProviderSpec(
                id=id or self._next_id("bedrock"),
                type="bedrock",
                model=ModelSpec(model_id=model),
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
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


__all__ = ["RobustChainBuilder", "SingleKeyProviderType"]
