# robust-llm-chain

<!-- CI badge will be enabled in Phase 3 once .github/workflows/ci.yml is in place -->
[![CI](https://img.shields.io/badge/CI-pending-lightgrey.svg)](https://github.com/jw1222/robust-llm-chain/actions)
[![PyPI](https://img.shields.io/badge/PyPI-0.1.0-blue.svg)](https://pypi.org/project/robust-llm-chain/)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 🇰🇷 한국어 문서: [README_KO.md](README_KO.md) · [ARCHITECTURE_KO.md](ARCHITECTURE_KO.md) · [CONTRIBUTING_KO.md](CONTRIBUTING_KO.md) · [SECURITY_KO.md](SECURITY_KO.md) · [CODE_OF_CONDUCT_KO.md](CODE_OF_CONDUCT_KO.md). 원본 (English) 이 정본.

> **Production-grade cross-vendor failover for LLM APIs.**
> When your provider hits 529 / pending / throttle, automatically retry on the next vendor — same request, sub-second detection, worker-coordinated round-robin.

`robust-llm-chain` is a small, focused Python library that adds **cross-vendor failover** to LLM API calls. It implements LangChain's `Runnable` interface, so it drops into existing chains, while exposing a richer `acall()` API for operational metadata (attempts, cost, usage).

It does one thing well: when Anthropic Direct returns 529 or stalls before the first token, the library transparently re-issues the same request to OpenRouter (or any other configured provider) — within seconds, not minutes.

---

## Why this exists

Two pains that off-the-shelf libraries address only partially:

### 1. Anthropic 529 / `Overloaded`
Anthropic Direct periodically returns `529 Overloaded` during demand spikes. A single retry against the same endpoint usually fails the same way. The right fix is cross-vendor failover — Claude is also reachable through Bedrock and OpenRouter — but most LLM client libraries only retry against the *same* provider.

### 2. Streaming "pending" provider
A provider can accept your request, hold the connection open, and never send the first token. With a 60-second total timeout, you wait the full minute before failing. With a 30-second timeout, you misclassify slow-but-real responses as failures.

`robust-llm-chain` separates the two:

- **`first_token_timeout` (default 15s)** — if no token arrives in this window, give up on this provider and try the next one. Fallback happens before the user notices a delay.
- **`per_provider_timeout` (default 60s)** — total response budget, applied after the first token has streamed.
- **`total_timeout`** — wall-clock cap across all attempts.

These two timeouts are the core differentiator: most libraries only have a single overall timeout, so a pending provider burns 30–60 seconds before fallback even starts.

---

## Quickstart

Install:
```bash
pip install "robust-llm-chain[anthropic,openrouter]"
```

Set two environment variables (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`), then:

```python
import asyncio
import os
from robust_llm_chain import RobustChain, ProviderSpec, ModelSpec

chain = RobustChain(providers=[
    ProviderSpec(
        id="anthropic-direct",                                    # your label
        type="anthropic",                                         # adapter
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),    # vendor's model id
        api_key=os.environ["ANTHROPIC_API_KEY"],
        priority=0,                                               # primary
    ),
    ProviderSpec(
        id="openrouter-claude",
        type="openrouter",
        model=ModelSpec(model_id="anthropic/claude-haiku-4.5"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        priority=1,                                               # fallback
    ),
])
# acall: convenience method that returns a ChainResult with operational metadata
result = asyncio.run(chain.acall("두 줄로 자기소개 해줘."))
print(result.output.content)                                # BaseMessage.content
print(f"used: {result.provider_used.id} | tokens: {result.usage}")  # metadata
```

> The standard Runnable `ainvoke()` returns just a `BaseMessage` (for LangChain composition). To get `attempts`, `cost`, and `usage` in one call, use `acall()` or read `chain.last_result`.

**What happens:**
- Two providers configured: Anthropic Direct (primary, `priority=0`) and OpenRouter as fallback (`priority=1`).
- If Anthropic returns 529 / overloaded / pending, the request transparently fails over to OpenRouter. No additional configuration.
- Distinct `id` (your label) and `model.model_id` (the vendor's identifier) so each role is unambiguous — even when OpenRouter's `vendor/model` format starts with `anthropic/...`.

**Defaults:** single-worker / `pricing=None` / `backend=LocalBackend()`. For multi-worker round-robin, cost computation, or multi-key / multi-region patterns, see [Advanced usage](#advanced-usage) below.

> **Shortcut for the simple "one provider per type" case:** `RobustChain.from_env(model_ids={"anthropic": "...", "openrouter": "..."})` auto-builds the same `ProviderSpec` list from env vars. Note the dict key is the **provider type** (adapter), and the value is the **vendor's model id** — these can look the same string when an OpenRouter model id starts with `anthropic/...`. Use the explicit form above when clarity matters.

---

## Anatomy of a result

`acall()` returns `ChainResult` — eight fields with everything you need to log, audit, and observe a call:

| Field | Type | What it carries |
|---|---|---|
| `output` | `BaseMessage` | The model's response (`output.content` is the text) |
| `input` | `list[BaseMessage]` | The normalized prompt actually sent (after `ChatPromptTemplate` rendering) |
| `usage` | `TokenUsage` | `input_tokens` / `output_tokens` / `cache_read_tokens` / `cache_write_tokens` / `total_tokens` |
| `cost` | `CostEstimate \| None` | USD per category — `None` when no `PricingSpec` is attached (cost tracking is opt-in) |
| `provider_used` | `ProviderSpec` | The provider that actually returned the response (the last attempt). Credentials are masked in `repr` |
| `model_used` | `ModelSpec` | The model spec of the successful provider |
| `attempts` | `list[AttemptRecord]` | Every provider attempt — successful and failed — in order. See below |
| `elapsed_ms` | `float` | End-to-end wall clock time |

### Happy path — single provider succeeds

```python
result = await chain.acall("두 줄로 자기소개 해줘.")

result.output.content              # → "안녕하세요. 저는 Claude 입니다. 두 줄로 자기소개 해 드릴게요."
result.usage                        # → TokenUsage(input_tokens=18, output_tokens=27, total_tokens=45, ...)
result.cost                         # → None  (no PricingSpec attached)
result.provider_used.id             # → "anthropic-direct"
result.provider_used.type           # → "anthropic"
result.model_used.model_id          # → "claude-haiku-4-5-20251001"
result.elapsed_ms                   # → 845.2
result.attempts                     # → [
                                    #     AttemptRecord(provider_id="anthropic-direct",
                                    #                   phase="model_creation", elapsed_ms=12,
                                    #                   error_type=None, fallback_eligible=False, ...),
                                    #     AttemptRecord(provider_id="anthropic-direct",
                                    #                   phase="first_token", elapsed_ms=320,
                                    #                   error_type=None, fallback_eligible=False, ...),
                                    #   ]
```

### Failover path — primary throttles, fallback succeeds

```python
result = await chain.acall("...")

result.output.content               # → response from OpenRouter
result.provider_used.id             # → "openrouter-claude"  (the one that succeeded)
result.attempts                     # → [
                                    #     AttemptRecord(provider_id="anthropic-direct",
                                    #                   phase="first_token", elapsed_ms=412,
                                    #                   error_type="OverloadedError",
                                    #                   error_message="529: Overloaded",
                                    #                   fallback_eligible=True, ...),
                                    #     AttemptRecord(provider_id="openrouter-claude",
                                    #                   phase="model_creation", elapsed_ms=8,
                                    #                   error_type=None, fallback_eligible=False, ...),
                                    #     AttemptRecord(provider_id="openrouter-claude",
                                    #                   phase="first_token", elapsed_ms=290,
                                    #                   error_type=None, fallback_eligible=False, ...),
                                    #   ]
```

`AttemptRecord.error_message` is **already sanitized** via `_security.sanitize_message` — provider key prefixes are masked and the string is truncated to 200 chars. Safe to log directly.

### `chain.last_result` (contextvars-scoped) and aggregates

| Property | What it carries |
|---|---|
| `chain.last_result` | The most recent `ChainResult` for **this `asyncio` task only** (`contextvars`-isolated, so concurrent `asyncio.gather(chain.acall(...), chain.acall(...))` calls don't see each other's results) |
| `chain.total_token_usage` | Cumulative `TokenUsage` across every successful call on this `RobustChain` instance (lock-protected) |
| `chain.total_cost` | Cumulative `CostEstimate` across every successful call (`None` until first call with pricing) |

The standard Runnable `ainvoke()` returns just a `BaseMessage`. To inspect `attempts` / `cost` / `usage` after `ainvoke` or `astream`, read `chain.last_result`.

---

## Logging

The library emits **structured WARN/ERROR-only logs** through Python's standard `logging` module. There is no DEBUG/INFO chatter, and **prompt or response text is never logged** — that is the application's responsibility (see [SECURITY.md](SECURITY.md) hardening #3).

### Logger names

| Logger | Source | When it fires |
|---|---|---|
| `robust_llm_chain.chain` | `RobustChain` instance + `from_env` | provider build failures, fallback attempts, unknown provider type warnings |
| `robust_llm_chain.observability.langsmith` | `cleanup_run` | LangSmith outage (timeout / generic exception), backpressure drops |

Both honor whatever handler / formatter / level you configure on the root logger or these specific names. To silence one, `logging.getLogger("robust_llm_chain.chain").setLevel(logging.ERROR)` etc.

### Structured fields (the `extra` payload)

Every WARN/ERROR record carries `extra` fields you can route in JSON formatters or aggregators (Datadog, Splunk, Loki, …):

| Event | Fields |
|---|---|
| `langsmith_cleanup_timeout` | `run_id` |
| `langsmith_cleanup_fail` | `run_id`, `error_type` |
| `langsmith_cleanup_drop` | `max_inflight` |

Custom logger inject: `RobustChain(providers=..., logger=my_logger)` — wire your own logger if you want a per-chain stream.

### What is NOT logged (by design)

- Prompt text (`input`) and response text (`output.content`) — application's `ChainResult.input` / `ChainResult.output` to persist if needed
- API keys / AWS credentials — `ProviderSpec.__repr__` masks them; `AttemptRecord.error_message` is sanitized via `_security.sanitize_message` before being stored
- Per-attempt success debug info — only WARN on failure / fallback events. Production-grade, low-cardinality

---

## Installation & Extras

> **What gets pulled in by default:** `langchain-core>=0.3` (transitive — provides `Runnable` / `BaseChatModel` / `BaseMessage` / `PromptValue` / `ChatPromptTemplate`). The umbrella `langchain` package is **intentionally NOT** a dependency — this library uses only the core abstractions, keeping the dependency footprint minimal. Provider SDKs (`langchain-anthropic` / `langchain-openai` / `langchain-aws`) and backends (`aiomcache`) are opt-in extras below.

| Command | What's included |
|---|---|
| `pip install robust-llm-chain` | Core only — `langchain-core` auto-pulled. No provider adapters, so `from_env()` raises `NoProvidersConfigured` until you add at least one extra |
| `pip install "robust-llm-chain[anthropic]"` | + `langchain-anthropic` (Anthropic Direct) |
| `pip install "robust-llm-chain[openrouter]"` | + `langchain-openai` (OpenRouter — OpenAI-compatible API) |
| `pip install "robust-llm-chain[openai]"` | + `langchain-openai` (OpenAI Direct) |
| `pip install "robust-llm-chain[bedrock]"` | + `langchain-aws` (AWS Bedrock — Claude / Llama / Nova / etc.) |
| `pip install "robust-llm-chain[memcached]"` | + `aiomcache` (async client for worker-coordinated round-robin) |
| `pip install "robust-llm-chain[anthropic,openrouter,bedrock,memcached]"` | Recommended v0.1 production combo (3-way Claude failover) |
| `pip install "robust-llm-chain[all]"` | Every adapter and backend shipped in v0.1 |

> A `redis` backend extra is planned for v0.2 — not yet shippable in v0.1, so the extra is intentionally absent from the list above.

The library does **not** depend on `python-dotenv`. Loading `.env` files is up to your application.

---

## Environment Variables

Recognized by `RobustChain.from_env()`:

| Variable | Provider | Active in v0.1 | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | anthropic | ✅ | Anthropic Direct |
| `OPENROUTER_API_KEY` | openrouter | ✅ | OpenRouter (any vendor's model) |
| `OPENAI_API_KEY` | openai | ✅ | OpenAI Direct (`gpt-*`, `o1-*`, etc.) |
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_REGION` | bedrock | ✅ | All three required; missing any one → provider skipped |

> **`from_env()` covers the simple "one provider per type" path.** For multi-key (e.g. primary + backup Anthropic keys) or multi-region (Bedrock east + west) patterns, build the `ProviderSpec` list explicitly — see [Advanced usage](#advanced-usage).

---

## Default Behavior

| Setting | Default | Meaning |
|---|---|---|
| `backend` | `LocalBackend()` (asyncio.Lock) | Single-worker safe round-robin |
| `per_provider_timeout` | `60s` | Total response budget per provider |
| `first_token_timeout` | `15s` | Fallback if first chunk doesn't arrive in this window |
| `total_timeout` | `per_provider × N + 60s buffer`, capped at `360s` | Wall-clock cap across all attempts |
| `stream_cleanup_timeout` | `2s` | `aclose()` budget when falling back during streaming |
| `temperature` | `0.1` | Per-call override available |
| `max_output_tokens` | `ModelSpec.max_output_tokens` or `4096` | Per-call override available |
| `pricing` | `None` → `result.cost = None` | Cost computation skipped without pricing |
| Logger name | `"robust_llm_chain"` | Hierarchical (e.g. `robust_llm_chain.stream`) |
| Logger level | `WARNING` | Set to `INFO`/`DEBUG` for fallback diagnostics |
| Type hints | `py.typed` marker shipped | mypy/pyright recognize types out of the box |
| `chain.invoke()` (sync) | not implemented in v0.1 | Wrap with `asyncio.run()` |

**Philosophy:** zero environment variables, zero external files required. `RobustChain(...)` runs immediately.

---

## Three things that make this different

1. **Streaming first-token timeout for pending detection.**
   Most libraries only have an overall timeout. A pending provider burns the full window before fallback. This library measures the *first chunk* arrival separately (default 15s) and falls over the moment that budget elapses.

2. **Worker-coordinated round-robin.** (v0.1: Memcached, v0.2: Redis)
   In a multi-worker deployment (gunicorn × 8, etc.), most OSS libraries hold the round-robin index per process. With 8 workers that means 8 simultaneous requests can land on the same provider. This library shares the index through a backend (Memcached or your own implementation of `IndexBackend`) so the load actually spreads.

3. **Cross-vendor (and cross-model) failover.**
   Same prompt, multiple paths. v0.1 active providers: **Anthropic Direct + OpenRouter + OpenAI Direct + AWS Bedrock**. Common patterns:
   - **Same-model 3-way failover** for Claude — Anthropic Direct ↔ Bedrock (us-east-1) ↔ OpenRouter
   - **Cross-region** within Bedrock — `id="bedrock-east"` (`us-east-1`) ↔ `id="bedrock-west"` (`us-west-2`)
   - **Cross-vendor cross-model** — Claude on Anthropic ↔ GPT on OpenAI when "we just need *some* answer"
   - **Multi-key per vendor** — `id="anthropic-primary"` ↔ `id="anthropic-backup"` for tenant isolation or rate-limit headroom

---

## Who is this for

- Long-running multi-worker Python services (FastAPI + gunicorn, Django, Celery)
- Teams running Claude across **multiple paths** (Anthropic Direct + Bedrock + OpenRouter), or mixing **Claude + GPT** for survivability
- Anyone who has actually been paged at 3am because of `529 Overloaded` or stalled streams
- Existing LangChain `Runnable` users — drop-in compatible

**Not for:** serverless / Edge runtimes, single-provider stacks, multimodal-first workloads.

---

## Compared to other libraries

| Library | What it does | What this library adds on top |
|---|---|---|
| **[litellm](https://github.com/BerriAI/litellm)** | Comprehensive multi-provider router with weighted / cost-based routing | Narrower scope: cross-vendor failover, first-token timeout, worker-coordinated round-robin |
| **LangChain `Runnable.with_fallbacks`** | Sequential exception-based fallback inside one Runnable | Adds first-token timeout (sub-second pending detection) + inter-worker round-robin via shared backend |
| **[Vercel AI SDK](https://github.com/vercel/ai)** | TypeScript/edge-first SDK with streaming UX | This is async Python for long-running multi-worker servers — different runtime target |

For most users the answer is **"use both"**: this library handles the cross-vendor failover layer, while litellm handles broader routing if you have it. They compose — `robust-llm-chain` is a single `Runnable` you can plug anywhere.

---

## Advanced usage

> **Runnable examples:** all four patterns below — multi-key, 3-way Claude failover, cross-vendor (Claude → GPT), Bedrock multi-region — are runnable scripts in [`examples/advanced.py`](examples/advanced.py). Try with `uv run python examples/advanced.py multikey` (or `3way` / `xvendor` / `multiregion`).

### Multi-worker production (Memcached-coordinated round-robin)
```python
import aiomcache
from robust_llm_chain import RobustChain
from robust_llm_chain.backends import MemcachedBackend

memcached = aiomcache.Client("memcached.internal", 11211)
chain = RobustChain.from_env(
    model_ids={
        "anthropic":  "claude-haiku-4-5-20251001",
        "openrouter": "anthropic/claude-haiku-4.5",
    },
    backend=MemcachedBackend(client=memcached, key_prefix="myapp:rr"),
)
```

> **Memcached failure semantics: fail-closed.** If Memcached is unreachable, the library raises `BackendUnavailable` rather than silently falling back to a local index. The whole point of the worker-coordinated round-robin is consistency across workers; an automatic fallback would silently break that. Catch the error in your app and decide explicitly (healthcheck-then-rebuild-chain pattern recommended).

### Explicit `ProviderSpec` (when env-based config isn't enough)
```python
import os
from robust_llm_chain import RobustChain, ProviderSpec, ModelSpec, PricingSpec, TimeoutConfig

chain = RobustChain(
    providers=[
        ProviderSpec(
            id="anthropic-direct",
            type="anthropic",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=ModelSpec(
                model_id="claude-haiku-4-5-20251001",
                pricing=PricingSpec(input_per_1m=0.80, output_per_1m=4.00),
                max_output_tokens=8192,
            ),
        ),
        ProviderSpec(
            id="openrouter",
            type="openrouter",
            api_key=os.environ["OPENROUTER_API_KEY"],
            model=ModelSpec(
                model_id="anthropic/claude-haiku-4.5",
                pricing=PricingSpec(input_per_1m=1.00, output_per_1m=5.00),
            ),
        ),
    ],
    timeouts=TimeoutConfig(per_provider=60.0, first_token=15.0),
)
```

### Multiple keys per vendor (primary + backup)
```python
import os
from robust_llm_chain import RobustChain, ProviderSpec, ModelSpec

# Two Anthropic API keys — round-robin between them, fall over if one rate-limits.
chain = RobustChain(providers=[
    ProviderSpec(
        id="anthropic-primary",
        type="anthropic",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
    ),
    ProviderSpec(
        id="anthropic-backup",
        type="anthropic",
        api_key=os.environ["ANTHROPIC_API_KEY_BACKUP"],
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),
    ),
])
```

### Bedrock cross-region failover (us-east-1 ↔ us-west-2)
```python
import os
from robust_llm_chain import RobustChain, ProviderSpec, ModelSpec

chain = RobustChain(providers=[
    ProviderSpec(
        id="bedrock-east",
        type="bedrock",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region="us-east-1",
        model=ModelSpec(model_id="anthropic.claude-haiku-4-5-20251001-v1:0"),
    ),
    ProviderSpec(
        id="bedrock-west",
        type="bedrock",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region="us-west-2",
        model=ModelSpec(model_id="anthropic.claude-haiku-4-5-20251001-v1:0"),
    ),
])
```

### Cross-vendor same-model: 3-way Claude (Anthropic + Bedrock + OpenRouter)
```python
chain = RobustChain.from_env(model_ids={
    "anthropic":  "claude-haiku-4-5-20251001",
    "bedrock":    "anthropic.claude-haiku-4-5-20251001-v1:0",
    "openrouter": "anthropic/claude-haiku-4.5",
})
# Round-robin between three paths to Claude. If Anthropic 529s, fall to
# Bedrock or OpenRouter automatically.
```

### Cross-vendor cross-model: Claude → GPT
```python
chain = RobustChain.from_env(model_ids={
    "anthropic": "claude-haiku-4-5-20251001",
    "openai":    "gpt-4o-mini",
})
# When "we just need some answer" matters more than "exactly the same model".
```

### Streaming
```python
async for chunk in chain.astream("Tell me a joke."):
    print(chunk.content, end="", flush=True)

# After completion, metadata is available
print(chain.last_result.attempts, chain.last_result.cost)
```

### Error handling
```python
from robust_llm_chain.errors import (
    AllProvidersFailed, ProviderTimeout, FallbackNotApplicable, BackendUnavailable,
)

try:
    result = await chain.acall("...")
except BackendUnavailable as e:
    # Memcached down — switch to LocalBackend explicitly or fail the request
    log.error("backend unavailable", extra={"error": str(e)})
except FallbackNotApplicable:
    # Auth error or parser failure — no point retrying
    raise
except AllProvidersFailed as e:
    for attempt in e.attempts:
        log.error("provider failed", extra={"provider": attempt.provider_id, "error": attempt.error_type})
except ProviderTimeout as e:
    log.error(f"total timeout in phase={e.phase}")
```

---

## Architecture

Module structure, dependency graph, call lifecycle (`acall` / `ainvoke` / `astream`), error flow, and extension points (custom `ProviderAdapter` / `IndexBackend`) are documented in [ARCHITECTURE.md](ARCHITECTURE.md). Read that before opening a PR or wiring a custom adapter.

---

## Status

**v0.1 is in active development.** Tested on **Python 3.13 only** (3.12 / 3.11 will be added in v0.2 / v1.0). Public API may break before 1.0; all changes will be documented in [CHANGELOG.md](CHANGELOG.md).

This is a personal project optimized for the maintainer's own dogfooding. External contributions are welcome but not depended on.

---

## License

MIT. See [LICENSE](LICENSE).
