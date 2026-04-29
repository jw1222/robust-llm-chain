# Architecture

> What lives where in `robust-llm-chain` and how a single call flows through it. Pair with [README.md](README.md) (usage) and [CHANGELOG.md](CHANGELOG.md) (history).

This document is the contract for **module structure / dependency graph / call lifecycle / data flow / error propagation / extension points**. If you are extending the library (new provider, new backend, new observability sink) start here.

---

## 1. Directory tree (source of truth)

```
robust-llm-chain/
├── README.md                          # usage + 30-second quickstart
├── ARCHITECTURE.md                    # this file
├── CHANGELOG.md
├── LICENSE                            # MIT
├── pyproject.toml                     # PEP 621, hatchling, ruff/mypy/pytest
├── uv.lock                            # committed (reproducible)
├── .python-version                    # 3.13.x
├── .env.example                       # placeholder env vars
├── Makefile                           # uv run shortcuts
├── .github/workflows/ci.yml           # GitHub Actions CI
├── examples/
│   └── quickstart.py                  # README quickstart, runnable
├── src/robust_llm_chain/
│   ├── __init__.py                    # public API (__all__ + __version__)
│   ├── py.typed                       # PEP 561 marker
│   ├── _security.py                   # key-pattern sanitizer (private)
│   ├── types.py                       # all public dataclasses + RobustChainInput alias
│   ├── errors.py                      # exception hierarchy + is_fallback_eligible
│   ├── chain.py                       # RobustChain — orchestrator + Hybrid API
│   ├── stream.py                      # StreamExecutor — first_token / chunks / cleanup
│   ├── resolver.py                    # ProviderResolver — round-robin selection
│   ├── cost.py                        # compute_cost — pure helper (USD per 1M tokens)
│   ├── adapters/
│   │   ├── __init__.py                # ProviderAdapter Protocol + registry + helpers
│   │   ├── anthropic.py               # AnthropicAdapter → ChatAnthropic
│   │   ├── openrouter.py              # OpenRouterAdapter → ChatOpenAI(base_url=...)
│   │   ├── openai.py                  # OpenAIAdapter → ChatOpenAI
│   │   └── bedrock.py                 # BedrockAdapter → ChatBedrockConverse
│   ├── backends/
│   │   ├── __init__.py                # IndexBackend Protocol + re-exports
│   │   ├── local.py                   # LocalBackend (asyncio.Lock)
│   │   └── memcached.py               # MemcacheClient Protocol + MemcachedBackend
│   ├── testing/
│   │   ├── __init__.py                # FakeAdapter, install_fake_adapter, ProviderOverloaded
│   │   └── fake_adapter.py            # FakeAdapter implementation
│   └── observability/
│       └── langsmith.py               # cleanup_run — Semaphore(50) backpressure
└── tests/
    ├── conftest.py                    # registry reset + key-based skip
    ├── test_*.py                      # unit (FakeAdapter; no network)
    ├── integration/test_*.py          # real SDK calls (auto-skip without keys)
    └── e2e/test_*.py                  # multi-provider real failover scenarios
```

Each file has one job. The `chain.py` orchestrator is the only module that touches every other layer; everything else has narrow, single-purpose dependencies.

---

## 2. Module dependency graph

Internal imports only (external `langchain_core` / `langchain_anthropic` / etc. excluded). `A → B` means *A imports B*.

```
Layer 0  _security                                         (no deps)
              │
              ▼
Layer 1  types                       ← _security (used by ProviderSpec.__repr__)
              │
              ▼
Layer 2  errors                      ← types (AttemptRecord on AllProvidersFailed)
         backends/__init__           (IndexBackend Protocol — pure)
         adapters/__init__           ← types (ProviderAdapter Protocol)
              │
              ▼
Layer 3  backends/local              ← backends/__init__
         backends/memcached          ← backends/__init__, errors
         adapters/{anthropic,openrouter,openai,bedrock}
                                     ← adapters/__init__, types, errors
         testing/fake_adapter        ← adapters/__init__, types
         observability/langsmith     (no internal deps)
         stream                      ← types, errors
              │
              ▼
Layer 4  resolver                    ← types, errors, backends/__init__
         testing/__init__            ← testing/fake_adapter, adapters/__init__
              │
              ▼
Layer 4½ cost                        ← types
              │
              ▼
Layer 5  chain                       ← types, errors, stream, resolver, cost,
                                       adapters/{__init__, anthropic, openrouter,
                                                 openai, bedrock},
                                       backends/{__init__, local}, _security,
                                       observability/langsmith
              │
              ▼
Layer 6  __init__                    (re-exports — public surface)
```

### Cycle-free invariants

- `types` depends only on `_security`.
- `errors` depends only on `types`.
- Sibling adapters don't import each other; same for sibling backends.
- `chain` imports concrete `LocalBackend` (default) but only depends on the `IndexBackend` *Protocol* — alternate backends inject through the constructor (DIP).
- `MemcachedBackend` depends on the `MemcacheClient` *Protocol*, never `aiomcache` directly.

### External dependency matrix

| Module | langchain-core | langchain-anthropic | langchain-openai | langchain-aws | aiomcache | langsmith |
|---|---|---|---|---|---|---|
| `types`, `errors`, `_security`, `cost` | — | — | — | — | — | — |
| `chain`, `stream`, `resolver` | ✓ (Runnable / messages) | — | — | — | — | — |
| `adapters/anthropic` | ✓ | ✓ (extra) | — | — | — | — |
| `adapters/openrouter`, `adapters/openai` | ✓ | — | ✓ (extra) | — | — | — |
| `adapters/bedrock` | ✓ | — | — | ✓ (extra) | — | — |
| `backends/local` | — | — | — | — | — | — |
| `backends/memcached` | — | — | — | — | Protocol only | — |
| `testing/fake_adapter` | ✓ | — | — | — | — | — |
| `observability/langsmith` | — | — | — | — | — | ✓ (env-gated) |

Provider/backend deps are all optional extras. Core install pulls only `langchain-core`.

---

## 3. Call lifecycle

Every public entry point (`acall`, `ainvoke`, `astream`) routes through `StreamExecutor` so the **first-token timeout** applies to all paths — that's the library's main differentiator.

### 3.1 Common path — `_run_with_failover`

```
chain.{ainvoke|astream|acall}                         entry
    │
    ▼
1. Input normalization (str / list[BaseMessage] / PromptValue / ChatPromptTemplate)
    │   → list[BaseMessage]; TypeError on unsupported
    ▼
2. Provisional ChainResult (attempts=[], output=AIMessage(""))   (astream commits immediately)
    │
    ▼
3. asyncio.wait_for(total_timeout)                    total = per_provider × N + 60s, cap 360s
    │
    ▼
4. attempt_order = await resolver.iterate()           one IndexBackend tick → priority-sorted
                                                      rotation (each provider exactly once)
   for spec in attempt_order:
       a. model = adapter.build(spec).bind(           per-call max_tokens / temperature
                       max_tokens=..., temperature=...)
       b. output, usage = await executor.collect(...) Phase 1: first_token wait
                                                      Phase 2: chunk pump (per_provider deadline)
                                                      Phase 3: bounded aclose() cleanup
       c. on success: break (record success attempt + build ChainResult)
          on FallbackEligible (is_fallback_eligible=True):
              record AttemptRecord(error_*) → continue
          on FallbackNotApplicable (auth, ModelNotFound, ...):
              record + raise immediately
    │
    ▼
5. Build ChainResult (input / output / usage / cost / provider_used / attempts / elapsed_ms)
    │
    ▼
6. _LAST_RESULT.set(result)        contextvars per-call isolation
   _update_totals(result)          asyncio.Lock-protected accumulation
    │
    ▼
7. Return  (ainvoke→msg, astream→AsyncIterator, acall→ChainResult)

   Exceptional exits:
   • all eligible failures exhausted → AllProvidersFailed(attempts) raise
   • total_timeout exceeded         → ProviderTimeout(phase="total") raise
   • last_result still committed with whatever was collected (partial diagnosis)
```

### 3.2 `acall` — convenience

Common path + extras:
- `prompt: ChatPromptTemplate` accepted (`prompt.format_messages(**template_inputs)`).
- Keyword-only `max_tokens` / `temperature` / `config` separated from `**template_inputs` to avoid namespace clash.
- Returns `ChainResult` directly (no need to read `last_result`).

### 3.3 `ainvoke` — Runnable standard

Common path; returns `BaseMessage` only. Metadata lives in `chain.last_result`. `ChatPromptTemplate` not accepted (Runnable contract — use a pipeline `template | chain`).

### 3.4 `astream` — pre/post-commit semantics

Streaming has a five-stage `last_result` lifecycle that lets users diagnose partial failures:

```
astream entry
    │
    ▼
stage 1: provisional ChainResult committed (provider_used = first spec, output = "")
    │
    ▼
─── pre-commit phase (no chunks yielded yet) ───
for spec in providers:
    try: first = await first_token_wait(model)        first_token_timeout
    on ProviderTimeout / fallback-eligible:
        stage 2: append AttemptRecord; continue
    on success:
        stage 3: confirm provider_used = spec
─── post-commit phase ───
        yield first_chunk
        async for chunk in stream:
            accumulate usage; yield chunk
        on stream error mid-flight:
            stage 5: partial commit → raise StreamInterrupted (no fallback —
                    fallback would replay from chunk 0 and the user has
                    already seen a partial response)
        on complete:
            stage 4: final commit (usage / cost / output)
            return
```

**Pre-commit**: silent fallback — caller never sees the failed provider's chunks.
**Post-commit**: `StreamInterrupted` — caller decides whether to retry from scratch or accept the partial.

Even on `StreamInterrupted`, `chain.last_result` carries the partial output + attempts for diagnosis.

---

## 4. Data model

```
TokenUsage                              (mutable — supports __iadd__ accumulation)
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, total_tokens
        ▲
        │ used by
        │
PricingSpec    (frozen)              CostEstimate    (frozen)
  input_per_1m, output_per_1m,         input_cost, output_cost,
  cache_read_per_1m, cache_write_per_1m, cache_read_cost, cache_write_cost,
  currency                             total_cost, currency
        │
        │ owned by
        ▼
ModelSpec      (frozen)
  model_id, pricing, context_window, max_output_tokens, deprecated_at, metadata
        │
        │ owned by
        ▼
ProviderSpec   (frozen, slots=True)  — credential fields use repr=False + custom __repr__
  id, type, model, api_key, aws_access_key_id, aws_secret_access_key,
  region, priority
        │
        │ used by
        ▼
ChainResult    (mutable — astream stages mutate)
  input, output, usage, cost, provider_used, model_used, attempts, elapsed_ms
  ↳ field-by-field semantics + happy/failover sample: README "Anatomy of a result"
        │
        │ contains
        ▼
AttemptRecord  (frozen) × N
  provider_id, provider_type, model_id, phase, elapsed_ms,
  error_type, error_message (sanitized), fallback_eligible, run_id

TimeoutConfig  (frozen)
  per_provider=60, first_token=15, total=None (auto), stream_cleanup=2

RobustChainInput = str | PromptValue | list[BaseMessage]   (PEP 695 alias)
```

### Frozen vs mutable

- **Frozen** (`ProviderSpec`, `ModelSpec`, `PricingSpec`, `AttemptRecord`, `CostEstimate`, `TimeoutConfig`): externally exposed value objects, never change after construction.
- **Mutable** (`ChainResult`, `TokenUsage`): mutated during the call lifecycle (`astream` stages, `+=` accumulation).

### Credential masking (multi-layer)

`ProviderSpec` blocks credential leakage through most channels — see `SECURITY.md §1` for the authoritative list of covered / not-covered paths:
1. `field(repr=False)` on `api_key` / `aws_access_key_id` / `aws_secret_access_key` — keys excluded from default `repr`.
2. Custom `__repr__` ensures masking even if dataclass changes.
3. `slots=True` removes `__dict__` so `vars(spec)` cannot bypass.
4. `_security.sanitize_message` runs on `AttemptRecord.error_message` to scrub provider API key prefixes / AWS access key id format / LangSmith personal token format out of error text (best-effort — see `_security.py` `_KEY_PATTERNS` and `SECURITY.md §2` for limitations).
5. `field(compare=False)` on credential fields — excludes them from `__eq__` / `__hash__`, so pytest assertion introspection cannot print credential values in failure diffs.
6. Custom `__getstate__` / `__setstate__` — `pickle.dumps(spec)` (and `copy.copy` / `copy.deepcopy`, which use the same protocol) omits credentials from the serialized state and restores them as `None`.

**Not covered**: `dataclasses.asdict(spec)` / `astuple(spec)` traverse all fields unconditionally and expose credentials in plaintext. The same applies recursively to `asdict(ChainResult)` because `ChainResult.provider_used` holds a `ProviderSpec`. For logging or serialization use `repr(spec)` — never `asdict`.

---

## 5. Error flow

### 5.1 Hierarchy

```
RobustChainError                                    (base)
├── NoProvidersConfigured                           # zero active providers
├── ProviderInactive                                # extras installed, adapter not active in this version
├── ProviderTimeout(phase=…)                        # library-imposed timeout (first_token / stream / total / model_creation)
├── ProviderModelCreationFailed                     # adapter.build threw
├── ModelDeprecated                                 # provider says model is sunsetting
├── ModelNotFound                                   # 404 / unknown model id
├── FallbackNotApplicable                           # auth / parser — never retry
├── StreamInterrupted                               # post-commit stream error
├── BackendUnavailable                              # IndexBackend down (Memcached etc.) — fail-closed
└── AllProvidersFailed(attempts=[...])              # raised after every provider exhausted
```

All transformations preserve `__cause__` (`raise X from original_exc`). Public errors are importable from `robust_llm_chain.errors`.

### 5.2 `is_fallback_eligible` classification (3 stages)

```
exception E
    │
    ▼
1. typed library exception?
       ProviderTimeout, BackendUnavailable           → eligible
       FallbackNotApplicable, ModelDeprecated,       → not eligible
       ModelNotFound
    │
    ▼
2. SDK class name match? (no SDK import — type(exc).__name__)
       RateLimitError, OverloadedError,              → eligible
       APITimeoutError, ServiceUnavailableError,
       InternalServerError, APIConnectionError
       AuthenticationError, PermissionDeniedError,   → not eligible
       OutputParserException, ValidationError
    │
    ▼
3. keyword substring (str(exc).lower())
       "529", "overloaded", "rate_limit",            → eligible
       "throttl", "timeout", "connection",
       "network", "502", "503", "504"
       "401", "403", "auth", "api key",              → not eligible
       "invalid", "not found"
    │
    ▼
otherwise: not eligible (conservative — no fallback when in doubt)
```

### 5.3 Streaming branch

```
streaming exception E
├── pre-commit (before first chunk yielded)
│       → run is_fallback_eligible → silent fallback or raise
└── post-commit (after first chunk yielded)
        → StreamInterrupted(cause=E)  (no fallback — would replay)
```

---

## 6. Public API surface

### Root re-exports (`robust_llm_chain.<name>`)

| Symbol | Source |
|---|---|
| `RobustChain` | `chain.py` |
| `RobustChainInput` | `types.py` |
| `ProviderSpec`, `ModelSpec`, `PricingSpec` | `types.py` |
| `TokenUsage`, `CostEstimate` | `types.py` |
| `ChainResult`, `AttemptRecord` | `types.py` |
| `TimeoutConfig` | `types.py` |
| `__version__` | `__init__.py` |

### Subpath modules

```python
from robust_llm_chain.errors    import AllProvidersFailed, ProviderTimeout, BackendUnavailable, ...
from robust_llm_chain.errors    import is_fallback_eligible
from robust_llm_chain.backends  import IndexBackend, LocalBackend, MemcachedBackend, MemcacheClient
from robust_llm_chain.adapters  import (
    ProviderAdapter, register_adapter, get_adapter,
    DEFAULT_MAX_OUTPUT_TOKENS, env_api_key_credentials,
)
from robust_llm_chain.cost      import compute_cost
from robust_llm_chain.testing   import FakeAdapter, install_fake_adapter, ProviderOverloaded
```

Anything else (`_security.*`, `chain._normalize_*`, `_ADAPTER_REGISTRY`, etc.) is **internal** — leading underscore or undocumented = no compatibility promise.

---

## 7. Extension points

### 7.1 New provider adapter

Implement the `ProviderAdapter` Protocol and register:

```python
from typing import ClassVar
from collections.abc import Mapping
from langchain_core.language_models.chat_models import BaseChatModel

from robust_llm_chain.adapters import register_adapter
from robust_llm_chain.types import ProviderSpec

class MistralAdapter:
    type: ClassVar[str] = "mistral"

    def build(self, spec: ProviderSpec) -> BaseChatModel:
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(model=spec.model.model_id, api_key=spec.api_key)

    def credentials_present(self, env: Mapping[str, str]) -> dict[str, str] | None:
        return {"api_key": env["MISTRAL_API_KEY"]} if "MISTRAL_API_KEY" in env else None

register_adapter(MistralAdapter())
# Now ProviderSpec(type="mistral", ...) works the same as built-in adapters.
```

Built-in adapters (`anthropic`, `openrouter`, `openai`, `bedrock`) use exactly this Protocol — no special treatment.

### 7.2 New `IndexBackend` (round-robin storage)

For DynamoDB / Cloudflare KV / Redis (v0.2 ships) / etc., implement:

```python
class IndexBackend(Protocol):
    async def get_and_increment(self, key: str) -> int:
        """Atomic — return current index then add 1.
        Raise BackendUnavailable on failure (do NOT silently fallback)."""
    async def reset(self, key: str) -> None: ...
    async def close(self) -> None: ...

# Inject:
chain = RobustChain(providers=[...], backend=MyDynamoDBBackend(...))
```

`MemcachedBackend` depends only on a `MemcacheClient` Protocol; you can wrap any client with the right method shape (`get` / `add` / `incr` / `delete` / `close`).

### 7.3 fail-closed semantics for shared backends

When a shared-state backend (Memcached, future Redis) is down, the library raises `BackendUnavailable` — it does **not** silently fall back to `LocalBackend`. Auto-fallback would silently break worker-coordinated round-robin (multiple workers would start hammering the same provider).

Catch `BackendUnavailable` at the application layer and decide explicitly: rebuild the chain with `LocalBackend()`, fail the request, or trip a circuit breaker.

For users who genuinely want fail-open behaviour, write a thin wrapper:

```python
class FailoverBackend:
    def __init__(self, primary, fallback):
        self._primary, self._fallback = primary, fallback
    async def get_and_increment(self, key: str) -> int:
        try: return await self._primary.get_and_increment(key)
        except BackendUnavailable: return await self._fallback.get_and_increment(key)
    # … reset, close
```

---

## 8. Where things are tested

| Concern | Tests |
|---|---|
| Data model + masking | `tests/test_types.py` |
| Error hierarchy + classifier | `tests/test_errors.py` |
| Adapter registry | `tests/test_adapters_registry.py` |
| Built-in adapters (no SDK call) | `tests/test_adapters_{anthropic,openrouter,openai,bedrock}.py` |
| Resolver round-robin + priority | `tests/test_resolver.py` |
| Stream 3-phase | `tests/test_stream.py` |
| Backends (local + Memcached protocol) | `tests/test_local_backend.py`, `tests/test_memcached_backend.py` |
| LangSmith cleanup + backpressure | `tests/test_observability.py` |
| Chain orchestration (via FakeAdapter) | `tests/test_chain.py` |
| Public surface | `tests/test_public_api.py` |
| Real SDK happy paths | `tests/integration/test_*_happy.py` (auto-skip without keys) |
| Multi-provider real failover | `tests/e2e/test_failover_real.py` (auto-skip without keys) |

Unit tests use `FakeAdapter` (committed in `robust_llm_chain.testing`) — zero network calls. Integration/e2e auto-skip when the relevant `*_API_KEY` env var is unset.

---

## 9. Versioning compatibility

`ARCHITECTURE.md` describes the v0.x layout. Public API (everything in `__init__.__all__` and the documented subpaths) follows semver — breaking changes bump the minor in 0.x and require a deprecation cycle in 1.x+.

Internal modules (`_security`, `chain._helper`, `_ADAPTER_REGISTRY`, etc.) carry no compatibility promise even within a patch release. If you find yourself importing an internal symbol, open an issue — that's a signal we should expose it.
