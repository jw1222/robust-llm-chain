"""Fluent builder for ``RobustChain``.

Two methods cover every shape: ``add_provider(type=…)`` for single-key
providers (Anthropic / OpenAI / OpenRouter), and ``add_bedrock(...)`` for
the asymmetric Bedrock case (region + two credentials). Credentials are
passed as values — read them from env / Secrets Manager / Vault yourself;
the builder does not touch ``os.environ``. See README "Provider
configuration" + ``examples/builder.py`` for full patterns.
"""

from typing import TYPE_CHECKING, Any, Literal, Self, get_args

from robust_llm_chain.types import ModelSpec, ProviderSpec

if TYPE_CHECKING:
    from robust_llm_chain.chain import RobustChain


SingleKeyProviderType = Literal["anthropic", "openai", "openrouter"]
"""Providers whose only credential is a single ``api_key`` string."""

_SINGLE_KEY_TYPES: tuple[str, ...] = get_args(SingleKeyProviderType)


class RobustChainBuilder:
    """Collect ``ProviderSpec`` s by chained ``add_*`` calls, then ``.build()``."""

    def __init__(self) -> None:
        self._specs: list[ProviderSpec] = []

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
        Lower ``priority`` values are preferred (DNS MX / cron convention).
        """
        if type not in _SINGLE_KEY_TYPES:
            raise ValueError(
                f"Unknown single-key provider type {type!r}. "
                f"Expected one of {list(_SINGLE_KEY_TYPES)}; "
                f"for Bedrock, call add_bedrock() instead."
            )
        self._specs.append(
            ProviderSpec(
                id=id or f"{type}-{len(self._specs) + 1}",
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
        Lower ``priority`` values are preferred.
        """
        self._specs.append(
            ProviderSpec(
                id=id or f"bedrock-{len(self._specs) + 1}",
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

    def build(self, **kwargs: Any) -> "RobustChain":
        """Construct the ``RobustChain``. ``kwargs`` forward to ``RobustChain.__init__``.

        Raises ``NoProvidersConfigured`` (via ``RobustChain.__init__``) when
        no ``add_*`` was called.
        """
        from robust_llm_chain.chain import RobustChain

        return RobustChain(providers=self._specs, **kwargs)


__all__ = ["RobustChainBuilder", "SingleKeyProviderType"]
