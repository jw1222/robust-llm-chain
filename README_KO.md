# robust-llm-chain

> 🇰🇷 한국어 번역. 원본은 [README.md](README.md) 참조 — 원본이 정본이며, 번역과 원본이 다를 시 원본 우선.

<!-- CI 배지는 Phase 3 에서 .github/workflows/ci.yml 가 준비되면 활성화 예정 -->
[![CI](https://img.shields.io/badge/CI-pending-lightgrey.svg)](https://github.com/jw1222/robust-llm-chain/actions)
[![PyPI](https://img.shields.io/badge/PyPI-0.1.0-blue.svg)](https://pypi.org/project/robust-llm-chain/)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **LLM API 를 위한 프로덕션 등급 cross-vendor 페일오버.**
> 사용 중인 provider 가 529 / pending / throttle 에 걸리면, 동일한 요청을 다음 vendor 로 자동 재시도한다 — 1초 미만의 감지, worker 간 조율된 라운드 로빈.

`robust-llm-chain` 은 LLM API 호출에 **cross-vendor 페일오버** 를 더하는 작고 집중된 Python 라이브러리이다. LangChain 의 `Runnable` 인터페이스를 구현하여 기존 chain 에 그대로 끼워 넣을 수 있으며, 운영 메타데이터(시도 내역, 비용, 사용량)를 위한 더 풍부한 `acall()` API 를 함께 제공한다.

이 라이브러리가 잘 하는 일은 하나다 — Anthropic Direct 가 529 를 반환하거나 첫 토큰 도착 전에 멈추면, 동일한 요청을 OpenRouter (또는 설정된 다른 provider) 로 투명하게 다시 보낸다. 분 단위가 아니라 초 단위 안에.

---

## Why this exists

기성 라이브러리들이 부분적으로만 해결하는 두 가지 고통:

### 1. Anthropic 529 / `Overloaded`
Anthropic Direct 는 수요 급증 시 주기적으로 `529 Overloaded` 를 반환한다. 동일 endpoint 에 단순 재시도를 걸어도 보통 같은 결과로 실패한다. 올바른 해법은 cross-vendor 페일오버 — Claude 는 Bedrock 과 OpenRouter 로도 도달 가능 — 인데, 대부분의 LLM 클라이언트 라이브러리는 *동일* provider 에만 재시도한다.

### 2. Streaming "pending" provider
Provider 가 요청을 수락하고 연결을 열어둔 채 첫 토큰을 영영 보내지 않는 경우가 있다. total timeout 60초로 잡으면 실패로 떨어지기까지 1분을 그대로 기다린다. 30초로 잡으면 느리지만 정상인 응답을 실패로 오분류한다.

`robust-llm-chain` 은 이 둘을 분리한다:

- **`first_token_timeout` (default 15s)** — 이 구간에 토큰이 하나도 안 오면 이 provider 를 포기하고 다음으로 넘어간다. 사용자가 지연을 인지하기 전에 폴백이 일어난다.
- **`per_provider_timeout` (default 60s)** — 첫 토큰이 도착한 이후 적용되는 총 응답 예산.
- **`total_timeout`** — 모든 시도를 합친 wall-clock 상한.

이 두 timeout 의 분리가 핵심 차별점이다. 대부분의 라이브러리는 단일 overall timeout 만 가지므로, pending provider 한 곳에서 30~60초를 태운 뒤에야 폴백이 시작된다.

---

## Quickstart

설치:
```bash
pip install "robust-llm-chain[anthropic,openrouter]"
```

환경 변수 두 개(`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`)를 설정한 뒤:

```python
import asyncio
import os
from robust_llm_chain import RobustChain, ProviderSpec, ModelSpec

chain = RobustChain(providers=[
    ProviderSpec(
        id="anthropic-direct",                                    # 사용자 라벨
        type="anthropic",                                         # adapter
        model=ModelSpec(model_id="claude-haiku-4-5-20251001"),    # vendor 의 model id
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
# acall: 운영 메타데이터가 포함된 ChainResult 를 반환하는 편의 메서드
result = asyncio.run(chain.acall("두 줄로 자기소개 해줘."))
print(result.output.content)                                # BaseMessage.content
print(f"used: {result.provider_used.id} | tokens: {result.usage}")  # metadata
```

> 표준 Runnable `ainvoke()` 는 `BaseMessage` 만 반환한다 (LangChain 합성용). `attempts`, `cost`, `usage` 까지 한 번에 받으려면 `acall()` 을 사용하거나 `chain.last_result` 를 읽어라.

**무슨 일이 일어나는가:**
- 두 개의 provider 가 설정됨: Anthropic Direct (primary, `priority=0`) 와 폴백용 OpenRouter (`priority=1`).
- Anthropic 이 529 / overloaded / pending 에 걸리면 요청은 OpenRouter 로 투명하게 페일오버된다. 추가 설정 없음.
- `id` (사용자 라벨) 와 `model.model_id` (vendor 의 식별자) 를 분리해두어 — OpenRouter 의 `vendor/model` 형식이 `anthropic/...` 로 시작할 때조차 — 각 역할이 모호하지 않다.

**기본값:** single-worker / `pricing=None` / `backend=LocalBackend()`. multi-worker 라운드 로빈, 비용 계산, multi-key / multi-region 패턴은 아래 [Advanced usage](#advanced-usage) 참조.

> **간단한 "타입당 provider 하나" 케이스 단축:** `RobustChain.from_env(model_ids={"anthropic": "...", "openrouter": "..."})` 가 환경 변수로부터 동일한 `ProviderSpec` 리스트를 자동으로 빌드한다. dict key 는 **provider type** (adapter) 이고 value 는 **vendor 의 model id** 이다 — OpenRouter model id 가 `anthropic/...` 로 시작하면 두 문자열이 비슷하게 보일 수 있다. 명확성이 중요하면 위의 명시적 형태를 사용하라.

---

## Anatomy of a result

`acall()` 은 `ChainResult` 를 반환한다 — 호출 하나를 로깅 / 감사 / 관측하는 데 필요한 모든 것을 담은 8개 필드:

| Field | Type | What it carries |
|---|---|---|
| `output` | `BaseMessage` | 모델 응답 (`output.content` 가 텍스트) |
| `input` | `list[BaseMessage]` | 실제로 전송된 정규화된 prompt (`ChatPromptTemplate` 렌더링 후) |
| `usage` | `TokenUsage` | `input_tokens` / `output_tokens` / `cache_read_tokens` / `cache_write_tokens` / `total_tokens` |
| `cost` | `CostEstimate \| None` | 카테고리별 USD — `PricingSpec` 미부착 시 `None` (비용 추적은 opt-in) |
| `provider_used` | `ProviderSpec` | 실제로 응답을 반환한 provider (마지막 시도). 자격증명은 `repr` 에서 마스킹됨 |
| `model_used` | `ModelSpec` | 성공한 provider 의 model spec |
| `attempts` | `list[AttemptRecord]` | 모든 provider 시도 — 성공/실패 모두 — 시간 순. 아래 참조 |
| `elapsed_ms` | `float` | end-to-end wall clock 시간 |

### Happy path — 단일 provider 가 성공한 경우

```python
result = await chain.acall("두 줄로 자기소개 해줘.")

result.output.content              # → "안녕하세요. 저는 Claude 입니다. 두 줄로 자기소개 해 드릴게요."
result.usage                        # → TokenUsage(input_tokens=18, output_tokens=27, total_tokens=45, ...)
result.cost                         # → None  (PricingSpec 미부착)
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

### Failover path — primary 가 throttle, 폴백이 성공

```python
result = await chain.acall("...")

result.output.content               # → OpenRouter 응답
result.provider_used.id             # → "openrouter-claude"  (성공한 쪽)
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

`AttemptRecord.error_message` 는 **이미 `_security.sanitize_message` 로 정화되어 있다** — provider key prefix 들이 마스킹되고 문자열은 200자로 잘린다. 그대로 로깅해도 안전.

### `chain.last_result` (contextvars-scoped) 와 누적값

| Property | What it carries |
|---|---|
| `chain.last_result` | **이 `asyncio` task 한정** 가장 최근의 `ChainResult` (`contextvars` 격리, 따라서 동시 실행되는 `asyncio.gather(chain.acall(...), chain.acall(...))` 호출들이 서로의 결과를 보지 않는다) |
| `chain.total_token_usage` | 이 `RobustChain` 인스턴스의 모든 성공 호출에 대한 누적 `TokenUsage` (lock 보호) |
| `chain.total_cost` | 모든 성공 호출에 대한 누적 `CostEstimate` (pricing 이 첨부된 첫 호출 전까지는 `None`) |

표준 Runnable `ainvoke()` 는 `BaseMessage` 만 반환한다. `ainvoke` 또는 `astream` 후 `attempts` / `cost` / `usage` 를 보려면 `chain.last_result` 를 읽어라.

---

## Logging

본 라이브러리는 Python 표준 `logging` 모듈을 통해 **WARN/ERROR 한정 구조화 로그** 만 발생시킨다. DEBUG/INFO 잡담은 없으며, **prompt 또는 response 텍스트는 절대 로깅되지 않는다** — 이는 애플리케이션의 책임이다 (자세한 hardening 항목 #3 은 [SECURITY.md](SECURITY.md) 참조).

### Logger 이름

| Logger | Source | When it fires |
|---|---|---|
| `robust_llm_chain.chain` | `RobustChain` 인스턴스 + `from_env` | provider 빌드 실패, 폴백 시도, 알 수 없는 provider type 경고 |
| `robust_llm_chain.observability.langsmith` | `cleanup_run` | LangSmith 장애 (timeout / generic exception), backpressure drop |

둘 다 root logger 또는 위 이름들에 설정한 handler / formatter / level 을 그대로 따른다. 한쪽만 끄고 싶다면 `logging.getLogger("robust_llm_chain.chain").setLevel(logging.ERROR)` 등.

### 구조화 필드 (`extra` payload)

모든 WARN/ERROR 레코드는 JSON formatter 나 aggregator (Datadog, Splunk, Loki, …) 에서 라우팅 가능한 `extra` 필드를 함께 갖는다:

| Event | Fields |
|---|---|
| `langsmith_cleanup_timeout` | `run_id` |
| `langsmith_cleanup_fail` | `run_id`, `error_type` |
| `langsmith_cleanup_drop` | `max_inflight` |

커스텀 logger 주입: `RobustChain(providers=..., logger=my_logger)` — chain 마다 별도 stream 을 두고 싶다면 본인의 logger 를 연결하라.

### 의도적으로 로깅하지 않는 것

- Prompt 텍스트 (`input`) 와 response 텍스트 (`output.content`) — 필요하면 애플리케이션이 `ChainResult.input` / `ChainResult.output` 을 직접 영속화
- API key / AWS 자격증명 — `ProviderSpec.__repr__` 가 마스킹; `AttemptRecord.error_message` 는 저장 전에 `_security.sanitize_message` 로 정화됨
- 시도별 성공 디버그 정보 — 실패 / 폴백 이벤트에서만 WARN. 프로덕션 등급, 낮은 카디널리티

---

## Installation & Extras

> **기본으로 함께 설치되는 것:** `langchain-core>=0.3` (transitive — `Runnable` / `BaseChatModel` / `BaseMessage` / `PromptValue` / `ChatPromptTemplate` 제공). umbrella 인 `langchain` 패키지는 **의도적으로 dependency 에 포함하지 않음** — 이 라이브러리는 core abstraction 만 사용하므로 dependency footprint 를 최소로 유지. provider SDK (`langchain-anthropic` / `langchain-openai` / `langchain-aws`) 와 backend (`aiomcache`) 는 아래 extras 로 opt-in.

| Command | What's included |
|---|---|
| `pip install robust-llm-chain` | Core 만 — `langchain-core` 자동 설치. provider adapter 없음 → 최소 1개 extra 추가 전까지 `from_env()` 가 `NoProvidersConfigured` 발생 |
| `pip install "robust-llm-chain[anthropic]"` | + `langchain-anthropic` (Anthropic Direct) |
| `pip install "robust-llm-chain[openrouter]"` | + `langchain-openai` (OpenRouter — OpenAI 호환 API) |
| `pip install "robust-llm-chain[openai]"` | + `langchain-openai` (OpenAI Direct) |
| `pip install "robust-llm-chain[bedrock]"` | + `langchain-aws` (AWS Bedrock — Claude / Llama / Nova / 등) |
| `pip install "robust-llm-chain[memcached]"` | + `aiomcache` (worker 조율 라운드 로빈용 async 클라이언트) |
| `pip install "robust-llm-chain[anthropic,openrouter,bedrock,memcached]"` | 권장 v0.1 프로덕션 조합 (3-way Claude 페일오버) |
| `pip install "robust-llm-chain[all]"` | v0.1 에 포함된 모든 adapter 와 backend |

> `redis` backend extra 는 v0.2 에 예정 — v0.1 에서는 아직 출시 가능 상태가 아니므로 위 표에서 의도적으로 제외.

본 라이브러리는 `python-dotenv` 에 **의존하지 않는다**. `.env` 파일 로딩은 애플리케이션의 몫이다.

---

## Environment Variables

`RobustChain.from_env()` 가 인식하는 변수:

| Variable | Provider | Active in v0.1 | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | anthropic | ✅ | Anthropic Direct |
| `OPENROUTER_API_KEY` | openrouter | ✅ | OpenRouter (모든 vendor 의 model) |
| `OPENAI_API_KEY` | openai | ✅ | OpenAI Direct (`gpt-*`, `o1-*`, 등) |
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_REGION` | bedrock | ✅ | 셋 모두 필수; 하나라도 없으면 provider skip |

> **`from_env()` 는 단순한 "타입당 provider 하나" 경로를 커버한다.** Multi-key (예: primary + backup Anthropic key) 또는 multi-region (Bedrock east + west) 패턴은 `ProviderSpec` 리스트를 명시적으로 빌드해야 한다 — [Advanced usage](#advanced-usage) 참조.

---

## Default Behavior

| Setting | Default | Meaning |
|---|---|---|
| `backend` | `LocalBackend()` (asyncio.Lock) | Single-worker 안전 라운드 로빈 |
| `per_provider_timeout` | `60s` | provider 당 총 응답 예산 |
| `first_token_timeout` | `15s` | 이 구간에 첫 chunk 가 안 오면 폴백 |
| `total_timeout` | `per_provider × N + 60s 버퍼`, `360s` 상한 | 모든 시도를 합친 wall-clock 상한 |
| `stream_cleanup_timeout` | `2s` | 스트리밍 중 폴백 시 `aclose()` 예산 |
| `temperature` | `0.1` | 호출별 override 가능 |
| `max_output_tokens` | `ModelSpec.max_output_tokens` 또는 `4096` | 호출별 override 가능 |
| `pricing` | `None` → `result.cost = None` | pricing 없으면 비용 계산 skip |
| Logger 이름 | `"robust_llm_chain"` | 계층적 (예: `robust_llm_chain.stream`) |
| Logger level | `WARNING` | 폴백 진단을 보려면 `INFO`/`DEBUG` 로 |
| 타입 힌트 | `py.typed` 마커 동봉 | mypy/pyright 가 즉시 타입 인식 |
| `chain.invoke()` (sync) | v0.1 미구현 | `asyncio.run()` 으로 감쌀 것 |

**철학:** 환경 변수 0개, 외부 파일 0개 필수. `RobustChain(...)` 만으로 즉시 동작.

---

## Three things that make this different

1. **Pending 감지를 위한 streaming first-token timeout.**
   대부분의 라이브러리는 overall timeout 하나만 가진다. Pending provider 는 그 전체 윈도우를 다 태우고 나서야 폴백한다. 본 라이브러리는 *첫 chunk* 도착을 별도로 측정하고 (default 15s), 그 예산이 끝나는 즉시 폴백한다.

2. **Worker 조율 라운드 로빈.** (v0.1: Memcached, v0.2: Redis)
   다중 worker 배포 (gunicorn × 8, 등) 환경에서 대부분의 OSS 라이브러리는 라운드 로빈 인덱스를 프로세스마다 유지한다. 그러면 worker 8개일 때 동시에 8건이 동일 provider 로 떨어질 수 있다. 본 라이브러리는 인덱스를 backend (Memcached 또는 본인이 구현한 `IndexBackend`) 를 통해 공유하므로 부하가 실제로 분산된다.

3. **Cross-vendor (그리고 cross-model) 페일오버.**
   같은 prompt, 여러 경로. v0.1 활성 provider: **Anthropic Direct + OpenRouter + OpenAI Direct + AWS Bedrock**. 일반적인 패턴:
   - Claude 의 **same-model 3-way 페일오버** — Anthropic Direct ↔ Bedrock (us-east-1) ↔ OpenRouter
   - Bedrock 내 **cross-region** — `id="bedrock-east"` (`us-east-1`) ↔ `id="bedrock-west"` (`us-west-2`)
   - **Cross-vendor cross-model** — "어떤 답이라도 필요" 할 때, Anthropic 의 Claude ↔ OpenAI 의 GPT
   - **Vendor 당 multi-key** — 테넌트 격리 또는 rate-limit 여유 확보를 위해 `id="anthropic-primary"` ↔ `id="anthropic-backup"`

---

## Who is this for

- 장기 실행되는 multi-worker Python 서비스 (FastAPI + gunicorn, Django, Celery)
- Claude 를 **여러 경로**로 운영하는 팀 (Anthropic Direct + Bedrock + OpenRouter), 또는 생존성을 위해 **Claude + GPT** 를 섞는 팀
- `529 Overloaded` 또는 stalled stream 때문에 새벽 3시에 호출당해 본 적이 있는 모든 사람
- 기존 LangChain `Runnable` 사용자 — drop-in 호환

**이 라이브러리가 맞지 않는 경우:** serverless / Edge runtime, 단일 provider 스택, multimodal 우선 워크로드.

---

## Compared to other libraries

| Library | What it does | What this library adds on top |
|---|---|---|
| **[litellm](https://github.com/BerriAI/litellm)** | 가중치 / 비용 기반 라우팅을 갖춘 종합적인 multi-provider 라우터 | 더 좁은 범위: cross-vendor 페일오버, first-token timeout, worker 조율 라운드 로빈 |
| **LangChain `Runnable.with_fallbacks`** | 단일 Runnable 내부의 순차 예외 기반 폴백 | first-token timeout (1초 미만 pending 감지) + 공유 backend 를 통한 worker 간 라운드 로빈 추가 |
| **[Vercel AI SDK](https://github.com/vercel/ai)** | streaming UX 에 강한 TypeScript/edge 우선 SDK | 본 라이브러리는 장기 실행 multi-worker 서버를 위한 async Python 이다 — runtime target 이 다르다 |

대부분의 사용자에게 답은 **"둘 다 사용"** 이다 — 본 라이브러리가 cross-vendor 페일오버 레이어를 담당하고, litellm 이 이미 있다면 더 넓은 라우팅을 맡는다. 둘은 합성 가능하다 — `robust-llm-chain` 은 어디든 끼울 수 있는 단일 `Runnable` 이다.

---

## Advanced usage

> **실행 가능 예제:** 아래 4 가지 패턴 — multi-key, 3-way Claude 페일오버, cross-vendor (Claude → GPT), Bedrock multi-region — 은 [`examples/advanced.py`](examples/advanced.py) 에 실행 가능 스크립트로 들어 있다. `uv run python examples/advanced.py multikey` (또는 `3way` / `xvendor` / `multiregion`) 로 실행.

### Multi-worker 프로덕션 (Memcached 조율 라운드 로빈)
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

> **Memcached 실패 의미론: fail-closed.** Memcached 가 도달 불가하면 본 라이브러리는 조용히 local index 로 폴백하지 않고 `BackendUnavailable` 을 발생시킨다. Worker 조율 라운드 로빈의 본질은 worker 간 일관성이며, 자동 폴백은 그것을 조용히 깨뜨리기 때문이다. 애플리케이션에서 에러를 catch 하고 명시적으로 결정하라 (healthcheck-then-rebuild-chain 패턴 권장).

### 명시적 `ProviderSpec` (env 기반 설정으로 부족할 때)
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

### Vendor 당 다중 key (primary + backup)
```python
import os
from robust_llm_chain import RobustChain, ProviderSpec, ModelSpec

# Anthropic API key 두 개 — 둘 사이를 라운드 로빈, 한쪽이 rate-limit 에 걸리면 폴백.
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

### Bedrock cross-region 페일오버 (us-east-1 ↔ us-west-2)
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
# Claude 로 가는 세 가지 경로를 라운드 로빈. Anthropic 이 529 면
# 자동으로 Bedrock 또는 OpenRouter 로 폴백.
```

### Cross-vendor cross-model: Claude → GPT
```python
chain = RobustChain.from_env(model_ids={
    "anthropic": "claude-haiku-4-5-20251001",
    "openai":    "gpt-4o-mini",
})
# "정확히 같은 모델" 보다 "어떤 답이든 필요" 가 중요할 때.
```

### Streaming
```python
async for chunk in chain.astream("Tell me a joke."):
    print(chunk.content, end="", flush=True)

# 완료 후, metadata 사용 가능
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
    # Memcached down — LocalBackend 로 명시적 전환하거나 요청 실패 처리
    log.error("backend unavailable", extra={"error": str(e)})
except FallbackNotApplicable:
    # auth 에러 또는 parser 실패 — 재시도해봐야 의미 없음
    raise
except AllProvidersFailed as e:
    for attempt in e.attempts:
        log.error("provider failed", extra={"provider": attempt.provider_id, "error": attempt.error_type})
except ProviderTimeout as e:
    log.error(f"total timeout in phase={e.phase}")
```

---

## Architecture

모듈 구조, 의존성 그래프, 호출 lifecycle (`acall` / `ainvoke` / `astream`), error flow, 확장 지점 (custom `ProviderAdapter` / `IndexBackend`) 은 [ARCHITECTURE.md](ARCHITECTURE.md) 에 정리되어 있다. PR 을 열거나 custom adapter 를 연결하기 전에 읽어볼 것.

---

## Status

**v0.1 활성 개발 중.** **Python 3.13 만 테스트됨** (3.12 / 3.11 은 v0.2 / v1.0 에서 추가 예정). Public API 는 1.0 이전에 깨질 수 있으며, 모든 변경은 [CHANGELOG.md](CHANGELOG.md) 에 기록된다.

이는 메인테이너 본인의 dogfooding 을 우선하여 최적화된 개인 프로젝트이다. 외부 기여는 환영하지만 의존하지는 않는다.

---

## License

MIT. [LICENSE](LICENSE) 참조.
