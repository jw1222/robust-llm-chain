# Architecture

> 🇰🇷 한국어 번역. 원본은 [ARCHITECTURE.md](ARCHITECTURE.md) 참조 — 원본이 정본이며, 번역과 원본이 다를 시 원본 우선.

> `robust-llm-chain` 의 어디에 무엇이 있고, 단일 호출이 어떻게 흐르는가. 사용법은 [README.md](README.md), 변경 이력은 [CHANGELOG.md](CHANGELOG.md) 와 함께 본다.

이 문서는 **모듈 구조 / 의존성 그래프 / 호출 lifecycle / data flow / error 전파 / 확장 지점**의 계약서이다. 라이브러리를 확장하는 경우 (새 provider, 새 backend, 새 observability sink) 여기서 시작하라.

---

## 1. Directory tree (단일 진실 원천)

```
robust-llm-chain/
├── README.md                          # 사용법 + 30초 quickstart
├── ARCHITECTURE.md                    # 이 파일
├── CHANGELOG.md
├── LICENSE                            # MIT
├── pyproject.toml                     # PEP 621, hatchling, ruff/mypy/pytest
├── uv.lock                            # commit (재현 가능성)
├── .python-version                    # 3.13.x
├── .env.example                       # placeholder env vars
├── Makefile                           # uv run 단축키
├── .github/workflows/ci.yml           # GitHub Actions CI
├── examples/
│   └── quickstart.py                  # README quickstart, 실행 가능
├── src/robust_llm_chain/
│   ├── __init__.py                    # public API (__all__ + __version__)
│   ├── py.typed                       # PEP 561 마커
│   ├── _security.py                   # key-pattern sanitizer (private)
│   ├── types.py                       # 모든 public dataclass + RobustChainInput alias
│   ├── errors.py                      # 예외 계층 + is_fallback_eligible
│   ├── chain.py                       # RobustChain — 오케스트레이터 + Hybrid API
│   ├── stream.py                      # StreamExecutor — first_token / chunks / cleanup
│   ├── resolver.py                    # ProviderResolver — 라운드 로빈 선택
│   ├── cost.py                        # compute_cost — 순수 helper (1M 토큰당 USD)
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
│   │   └── fake_adapter.py            # FakeAdapter 구현
│   └── observability/
│       └── langsmith.py               # cleanup_run — Semaphore(50) backpressure
└── tests/
    ├── conftest.py                    # registry 리셋 + key 기반 skip
    ├── test_*.py                      # unit (FakeAdapter; 네트워크 없음)
    ├── integration/test_*.py          # 실제 SDK 호출 (key 없으면 자동 skip)
    └── e2e/test_*.py                  # 다중 provider 실제 페일오버 시나리오
```

각 파일은 한 가지 일을 한다. `chain.py` 오케스트레이터만이 다른 모든 레이어에 닿는 유일한 모듈이며, 나머지는 좁고 단일 목적의 의존성을 가진다.

---

## 2. Module dependency graph

내부 import 만 표시 (외부 `langchain_core` / `langchain_anthropic` / 등 제외). `A → B` 는 *A 가 B 를 import* 한다는 의미.

```
Layer 0  _security                                         (의존성 없음)
              │
              ▼
Layer 1  types                       ← _security (ProviderSpec.__repr__ 에서 사용)
              │
              ▼
Layer 2  errors                      ← types (AllProvidersFailed 위의 AttemptRecord)
         backends/__init__           (IndexBackend Protocol — 순수)
         adapters/__init__           ← types (ProviderAdapter Protocol)
              │
              ▼
Layer 3  backends/local              ← backends/__init__
         backends/memcached          ← backends/__init__, errors
         adapters/{anthropic,openrouter,openai,bedrock}
                                     ← adapters/__init__, types, errors
         testing/fake_adapter        ← adapters/__init__, types
         observability/langsmith     (내부 의존성 없음)
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

### 사이클 없음 불변 규칙

- `types` 는 `_security` 에만 의존.
- `errors` 는 `types` 에만 의존.
- 형제 adapter 들은 서로를 import 하지 않는다; 형제 backend 들도 마찬가지.
- `chain` 은 구체 `LocalBackend` (default) 를 import 하지만, `IndexBackend` *Protocol* 에만 의존한다 — 대안 backend 는 생성자로 주입한다 (DIP).
- `MemcachedBackend` 는 `MemcacheClient` *Protocol* 에 의존하며, `aiomcache` 에 직접 의존하지 않는다.

### 외부 의존성 매트릭스

| Module | langchain-core | langchain-anthropic | langchain-openai | langchain-aws | aiomcache | langsmith |
|---|---|---|---|---|---|---|
| `types`, `errors`, `_security`, `cost` | — | — | — | — | — | — |
| `chain`, `stream`, `resolver` | ✓ (Runnable / messages) | — | — | — | — | — |
| `adapters/anthropic` | ✓ | ✓ (extra) | — | — | — | — |
| `adapters/openrouter`, `adapters/openai` | ✓ | — | ✓ (extra) | — | — | — |
| `adapters/bedrock` | ✓ | — | — | ✓ (extra) | — | — |
| `backends/local` | — | — | — | — | — | — |
| `backends/memcached` | — | — | — | — | Protocol 만 | — |
| `testing/fake_adapter` | ✓ | — | — | — | — | — |
| `observability/langsmith` | — | — | — | — | — | ✓ (env-gated) |

Provider/backend 의존성은 모두 optional extra. Core 설치는 `langchain-core` 만 가져온다.

---

## 3. Call lifecycle

모든 public 진입점 (`acall`, `ainvoke`, `astream`) 은 `StreamExecutor` 를 거쳐 라우팅되어, **first-token timeout** 이 모든 경로에 적용된다 — 이것이 본 라이브러리의 주된 차별점이다.

### 3.1 공통 경로 — `_run_with_failover`

```
chain.{ainvoke|astream|acall}                         진입
    │
    ▼
1. 입력 정규화 (str / list[BaseMessage] / PromptValue / ChatPromptTemplate)
    │   → list[BaseMessage]; 미지원 시 TypeError
    ▼
2. 임시 ChainResult (attempts=[], output=AIMessage(""))   (astream 은 즉시 commit)
    │
    ▼
3. asyncio.wait_for(total_timeout)                    total = per_provider × N + 60s, 360s 상한
    │
    ▼
4. attempt_order = await resolver.iterate()           한 번의 IndexBackend tick → RR start (사용자
                                                      추가 순서) + priority-sorted fallback
                                                      (각 provider 정확히 1회)
   for spec in attempt_order:
       a. model = adapter.build(spec).bind(           호출별 max_tokens / temperature
                       max_tokens=..., temperature=...)
                                                      raw SDK exception 은 ProviderModelCreationFailed
                                                      로 wrap (typed contract, __cause__ 보존,
                                                      fallback eligible). 다른 RobustChainError
                                                      subclass (ProviderInactive / BackendUnavailable
                                                      등) 은 그대로 통과.
       b. output, usage = await executor.collect(...) Phase 1: first_token 대기
                                                      Phase 2: chunk pump (per_provider deadline)
                                                      Phase 3: 제한된 aclose() 정리
       c. 성공 시: break (성공 attempt 기록 + ChainResult 빌드)
          FallbackEligible (is_fallback_eligible=True) 시:
              AttemptRecord(error_*) 기록 → continue
          FallbackNotApplicable (auth, ModelNotFound, ...) 시:
              기록 + 즉시 raise
    │
    ▼
5. ChainResult 빌드 (input / output / usage / cost / provider_used / attempts / elapsed_ms)
    │
    ▼
6. _LAST_RESULT.set(result)        contextvars 호출별 격리
   _update_totals(result)          asyncio.Lock 보호 누적
    │
    ▼
7. 반환  (ainvoke→msg, astream→AsyncIterator, acall→ChainResult)

   예외적 종료:
   • 모든 eligible 실패 소진 → AllProvidersFailed(attempts) raise
   • total_timeout 초과         → ProviderTimeout(phase="total") raise
   • last_result 에는 그 시점까지 수집된 무엇이든 commit 된다 (부분 진단용)
```

### 3.2 `acall` — 편의 메서드

공통 경로 + 추가 사항:
- `prompt: ChatPromptTemplate` 허용 (`prompt.format_messages(**template_inputs)`).
- Keyword-only `max_tokens` / `temperature` / `config` 가 `**template_inputs` 와 분리되어 namespace 충돌 방지.
- `ChainResult` 를 직접 반환 (`last_result` 를 읽을 필요 없음).

### 3.3 `ainvoke` — Runnable 표준

공통 경로; `BaseMessage` 만 반환. 메타데이터는 `chain.last_result` 에 있음. `ChatPromptTemplate` 미허용 (Runnable 계약 — `template | chain` 파이프라인 사용).

### 3.4 `astream` — pre/post-commit 의미론

스트리밍은 부분 실패 진단을 가능하게 하는 5단계 `last_result` lifecycle 을 가진다:

```
astream 진입
    │
    ▼
stage 1: 임시 ChainResult commit (provider_used = first spec, output = "")
    │
    ▼
─── pre-commit phase (chunk yield 전) ───
for spec in providers:
    try: first = await first_token_wait(model)        first_token_timeout
    on ProviderTimeout / fallback-eligible:
        stage 2: AttemptRecord append; continue
    on success:
        stage 3: provider_used = spec 확정
─── post-commit phase ───
        yield first_chunk
        async for chunk in stream:
            usage 누적; chunk yield
        스트림 도중 에러:
            stage 5: 부분 commit → StreamInterrupted raise (폴백 없음 —
                    폴백은 chunk 0 부터 재생하게 되며 사용자는 이미
                    부분 응답을 본 상태)
        완료 시:
            stage 4: 최종 commit (usage / cost / output)
            return
```

**Pre-commit**: 조용한 폴백 — 호출자는 실패한 provider 의 chunk 를 절대 보지 않는다.
**Post-commit**: `StreamInterrupted` — 호출자가 처음부터 재시도할지, 부분을 받아들일지 결정.

`StreamInterrupted` 가 나도 `chain.last_result` 는 진단을 위한 부분 output + attempts 를 담고 있다.

---

## 4. Data model

```
TokenUsage                              (mutable — __iadd__ 누적 지원)
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, total_tokens
        ▲
        │ 사용처
        │
PricingSpec    (frozen)              CostEstimate    (frozen)
  input_per_1m, output_per_1m,         input_cost, output_cost,
  cache_read_per_1m, cache_write_per_1m, cache_read_cost, cache_write_cost,
  currency                             total_cost, currency
        │
        │ 소유
        ▼
ModelSpec      (frozen)
  model_id, pricing, context_window, max_output_tokens, deprecated_at, metadata
        │
        │ 소유
        ▼
ProviderSpec   (frozen, slots=True)  — 자격증명 필드는 repr=False + custom __repr__ 사용
  id, type, model, api_key, aws_access_key_id, aws_secret_access_key,
  region, priority
        │
        │ 사용처
        ▼
ChainResult    (mutable — astream 단계가 mutate)
  input, output, usage, cost, provider_used, model_used, attempts, elapsed_ms
  ↳ 필드별 의미론 + happy/failover 샘플: README "Anatomy of a result"
        │
        │ 포함
        ▼
AttemptRecord  (frozen) × N
  provider_id, provider_type, model_id, phase, elapsed_ms,
  error_type, error_message (sanitized), fallback_eligible, run_id

TimeoutConfig  (frozen)
  per_provider=60, first_token=15, total=None (auto), stream_cleanup=2

RobustChainInput = str | PromptValue | list[BaseMessage]   (PEP 695 alias)
```

### Frozen vs mutable

- **Frozen** (`ProviderSpec`, `ModelSpec`, `PricingSpec`, `AttemptRecord`, `CostEstimate`, `TimeoutConfig`): 외부 노출되는 value object, 생성 후 변하지 않음.
- **Mutable** (`ChainResult`, `TokenUsage`): 호출 lifecycle 동안 mutate 됨 (`astream` 단계, `+=` 누적).

### 자격증명 마스킹 (다층)

`ProviderSpec` 은 대부분의 채널에서 자격증명 유출을 차단한다 — 다루는/다루지 않는 경로의 권위 있는 목록은 `SECURITY.md §1` 참조:
1. `field(repr=False)` 가 `api_key` / `aws_access_key_id` / `aws_secret_access_key` 에 — 키가 default `repr` 에서 제외.
2. Custom `__repr__` 가 dataclass 가 바뀌어도 마스킹 보장.
3. `slots=True` 가 `__dict__` 를 제거 → `vars(spec)` 우회 불가.
4. `_security.sanitize_message` 가 `AttemptRecord.error_message` 위에서 동작하여 provider API key prefix / AWS access key id 형식 / LangSmith personal token 형식을 에러 텍스트에서 제거 (best-effort — 한계는 `_security.py` 의 `_KEY_PATTERNS` 와 `SECURITY.md §2` 참조).
5. `field(compare=False)` 가 자격증명 필드에 — `__eq__` / `__hash__` 에서 제외, 따라서 pytest assertion introspection 이 실패 diff 에 자격증명 값을 출력할 수 없다.
6. Custom `__getstate__` / `__setstate__` — `pickle.dumps(spec)` (그리고 동일 프로토콜을 쓰는 `copy.copy` / `copy.deepcopy`) 는 자격증명을 직렬화 상태에서 누락하고 `None` 으로 복원.

**다루지 않는 것**: `dataclasses.asdict(spec)` / `astuple(spec)` 은 모든 필드를 무조건 순회하여 자격증명을 평문으로 노출한다. 동일한 점이 `asdict(ChainResult)` 에도 재귀적으로 적용된다 — `ChainResult.provider_used` 가 `ProviderSpec` 을 들고 있기 때문. 로깅이나 직렬화에는 `repr(spec)` 을 쓰고 — 절대 `asdict` 를 쓰지 말 것.

---

## 5. Error flow

### 5.1 계층

```
RobustChainError                                    (base)
├── NoProvidersConfigured                           # 활성 provider 0개
├── ProviderInactive                                # extras 설치되었으나 이 버전에서 adapter 비활성
├── ProviderTimeout(phase=…)                        # 라이브러리가 부과한 timeout (first_token / stream / total / model_creation)
├── ProviderModelCreationFailed                     # adapter.build raise — raw SDK / config
│                                                     오류는 여기로 wrap (v0.4.1+); fallback eligible
│                                                     이라 다른 vendor 들 시도 계속. __cause__ 에
│                                                     원본 raw exception 보존.
├── ModelDeprecated                                 # provider 가 모델 sunset 통지
├── ModelNotFound                                   # 404 / 알 수 없는 model id
├── FallbackNotApplicable                           # auth / parser — 절대 재시도 안 함
├── StreamInterrupted                               # post-commit 스트림 에러
├── BackendUnavailable                              # IndexBackend down (Memcached 등) — fail-closed
└── AllProvidersFailed(attempts=[...])              # 모든 provider 소진 후 raise
```

모든 변환은 `__cause__` 를 보존한다 (`raise X from original_exc`). Public error 는 `robust_llm_chain.errors` 에서 import 가능.

### 5.2 `is_fallback_eligible` 분류 (3 단계)

```
exception E
    │
    ▼
1. typed library exception?
       ProviderTimeout, BackendUnavailable,          → eligible
       ProviderModelCreationFailed
       FallbackNotApplicable, ModelDeprecated,       → not eligible
       ModelNotFound
    │
    ▼
2. SDK 클래스 이름 매치? (SDK import 없음 — type(exc).__name__)
       RateLimitError, OverloadedError,              → eligible
       APITimeoutError, ServiceUnavailableError,
       InternalServerError, APIConnectionError
       AuthenticationError, PermissionDeniedError,   → not eligible
       OutputParserException, ValidationError
    │
    ▼
3. 키워드 substring (str(exc).lower())
       "529", "overloaded", "rate_limit",            → eligible
       "throttl", "timeout", "connection",
       "network", "502", "503", "504"
       "401", "403", "auth", "api key",              → not eligible
       "invalid", "not found"
    │
    ▼
그 외: not eligible (보수적 — 의심스러우면 폴백 없음)
```

### 5.3 Streaming 분기

```
streaming exception E
├── pre-commit (첫 chunk yield 전)
│       → is_fallback_eligible 실행 → 조용한 폴백 또는 raise
└── post-commit (첫 chunk yield 후)
        → StreamInterrupted(cause=E)  (폴백 없음 — 재생 발생)
```

---

## 6. Public API surface

### Root re-exports (`robust_llm_chain.<name>`)

| Symbol | Source |
|---|---|
| `RobustChain` | `chain.py` |
| `RobustChainBuilder`, `SingleKeyProviderType` | `builder.py` |
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

그 외 (`_security.*`, `chain._normalize_*`, `_ADAPTER_REGISTRY`, 등) 은 모두 **internal** — 선행 underscore 또는 미문서화 = 호환성 약속 없음.

---

## 7. Extension points

### 7.1 새 provider adapter

`ProviderAdapter` Protocol 을 구현하고 register:

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
# 이제 ProviderSpec(type="mistral", ...) 가 내장 adapter 와 동일하게 작동.
```

내장 adapter (`anthropic`, `openrouter`, `openai`, `bedrock`) 들은 정확히 이 Protocol 을 사용한다 — 특별 취급 없음.

### 7.2 새 `IndexBackend` (라운드 로빈 저장소)

DynamoDB / Cloudflare KV / Redis (v0.2 출시) / 등을 위해, 다음을 구현:

```python
class IndexBackend(Protocol):
    async def get_and_increment(self, key: str) -> int:
        """Atomic — 현재 인덱스를 반환한 뒤 1 증가.
        실패 시 BackendUnavailable raise (조용한 폴백 금지)."""
    async def reset(self, key: str) -> None: ...
    async def close(self) -> None: ...

# 주입:
chain = RobustChain(providers=[...], backend=MyDynamoDBBackend(...))
```

`MemcachedBackend` 는 `MemcacheClient` Protocol 에만 의존한다; 올바른 메서드 형태(`get` / `add` / `incr` / `delete` / `close`) 를 가진 어떤 클라이언트로도 감쌀 수 있다.

### 7.3 공유 backend 의 fail-closed 의미론

공유 상태 backend (Memcached, 향후 Redis) 가 down 일 때, 본 라이브러리는 `BackendUnavailable` 을 발생시킨다 — `LocalBackend` 로 **조용히** 폴백하지 **않는다**. 자동 폴백은 worker 조율 라운드 로빈을 조용히 깨뜨릴 것이기 때문 (여러 worker 가 동일 provider 를 두드리기 시작).

애플리케이션 레이어에서 `BackendUnavailable` 을 catch 하고 명시적으로 결정하라: `LocalBackend()` 로 chain 을 재구성, 요청을 실패 처리, 또는 circuit breaker 트립.

진짜로 fail-open 동작을 원하는 사용자는 얇은 wrapper 를 쓰면 된다:

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

## 8. 테스트 위치

| Concern | Tests |
|---|---|
| Data model + 마스킹 | `tests/test_types.py` |
| Error 계층 + 분류기 | `tests/test_errors.py` |
| Adapter registry | `tests/test_adapters_registry.py` |
| 내장 adapter (SDK 호출 없음) | `tests/test_adapters_{anthropic,openrouter,openai,bedrock}.py` |
| Resolver 라운드 로빈 + priority | `tests/test_resolver.py` |
| Stream 3-phase | `tests/test_stream.py` |
| Backends (local + Memcached protocol) | `tests/test_local_backend.py`, `tests/test_memcached_backend.py` |
| LangSmith cleanup + backpressure | `tests/test_observability.py` |
| Chain 오케스트레이션 (FakeAdapter 통해) | `tests/test_chain.py` |
| Public surface | `tests/test_public_api.py` |
| 실제 SDK happy path | `tests/integration/test_*_happy.py` (key 없으면 자동 skip) |
| 다중 provider 실제 페일오버 | `tests/e2e/test_failover_real.py` (key 없으면 자동 skip) |

Unit test 는 `FakeAdapter` 를 사용 (`robust_llm_chain.testing` 에 commit 됨) — 네트워크 호출 0건. integration/e2e 는 해당 `*_API_KEY` env var 가 unset 이면 자동 skip.

---

## 9. Versioning 호환성

`ARCHITECTURE.md` 는 v0.x 레이아웃을 기술한다. Public API (`__init__.__all__` 의 모든 것 + 문서화된 subpath) 는 semver 를 따른다 — breaking change 는 0.x 에서 minor 를 올리고, 1.x+ 에서는 deprecation cycle 을 요구한다.

내부 모듈 (`_security`, `chain._helper`, `_ADAPTER_REGISTRY`, 등) 은 patch 릴리즈 안에서도 호환성 약속이 없다. 만약 internal symbol 을 import 하는 자신을 발견한다면 issue 를 열어라 — 그것은 우리가 노출해야 한다는 신호다.
