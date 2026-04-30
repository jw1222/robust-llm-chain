# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식, [Semantic Versioning](https://semver.org/) 준수.

## [Unreleased]

### v0.5 backlog — 외부 senior review (2026-04-30) 후속

- **adapter build 오류 표준화**: `ProviderModelCreationFailed` (errors.py:37) 가 정의만 있고 raise 0건. SDK validation/config 오류가 raw exception 으로 새는 상태. `chain._build_model` 에서 wrap 적용. wrap 대상 exception 범위는 v0.5 설계 시 결정. v0.2 backlog #11 과 동일.
- **observability hookup**: `observability/langsmith.py::cleanup_run` 헬퍼는 정의되어 있으나 `chain.py` failover loop 에서 호출 0건 + `_record_attempt(run_id=None)` hardcode. 적용하려면 `RunnableConfig` 에서 run_id 추출 패턴 정립 필요. LangSmith 자동 트레이싱은 작동 (Runnable 호환) 하나 fallback 발생 시 pending run cleanup 안 됨.
- **version SSoT** (`pyproject.toml:7` + `__init__.py:23` 중복 → hatchling-vcs 같은 dynamic version): release 자동화와 묶어서 처리.

## [0.4.0] - 2026-04-30

### Changed (BREAKING) — Failover semantic: RR start + priority-ordered fallback

`ProviderResolver.iterate()` 가 두 역할을 명확히 분리:

* **Round-robin** — 이번 호출의 *첫* provider 를 선택 (사용자 추가 순서 위에서 회전).
* **Priority** — 첫 provider 실패 후 *fallback 순서* 결정 (낮은 값이 우선, 호출마다 동일).

이전 (v0.3.x): priority-sorted 단일 리스트를 RR index 만큼 회전 (`providers[start:] + providers[:start]`). 결과적으로 **fallback 순서가 매 호출마다 회전과 함께 바뀜** — provider 들이 서로 다른 priority 를 가질 때 fallback 은 엄밀히 priority-sorted 가 아니었음.

예시 (`[A(p=0), B(p=1), C(p=2)]`):

| Call | v0.3 (회전) | v0.4 (RR start + priority fallback) |
|---|---|---|
| 1 | `A → B → C` | `A → B → C` |
| 2 | `B → C → A` | `B → A → C` |
| 3 | `C → A → B` | `C → A → B` |

호출 2 에서 차이 — v0.3 은 `B` 실패 시 `C` 로 폴백 (rotation 순), v0.4 는 `A` 로 폴백 (priority 순). v0.4 가 "fallback 은 항상 priority 가 낮은 쪽으로" 라는 일반적/직관적 LB 정의와 일치.

**왜 v0.4 인가**: 사용자 dogfooding 에서 의도된 정책이 "RR = 트래픽 분산, Priority = 폴백 선호 순서" 인데 v0.3.x 구현은 priority 가 정렬 보조 역할만 하고 fallback 단계에서 의미가 사라지는 회전이었음을 발견. 코드가 documented intent 와 다르고, 회전 의미는 documentation 에만 명시되어 있던 부수 효과.

**마이그레이션**:
- 진정한 no-op 은 **`n=1` (provider 1개)** 뿐.
- **`n=2`**: 사용자 추가 순서가 priority 순서와 일치하면 (예: `[A(p=0), B(p=1)]`) v0.3/v0.4 동일. **다르면 swap** — 예: 사용자가 `[B(p=1), A(p=0)]` 로 추가하면 v0.3 호출 1 = `[A,B]` (priority-sorted rotation), v0.4 호출 1 = `[B,A]` (RR start = user-listed 첫 항목 B + priority fallback `[A]`).
- **`n≥3`**: priority 가 모두 같아도 fallback 순서가 변함. 예시 `[A,B,C]` 모두 priority=0, 호출 2 에서 v0.3 = `[B,C,A]` (rotation), v0.4 = `[B,A,C]` (RR-start B + priority-sorted fallback `[A,C]`).
- **공통**: RR 첫 시도 분산은 v0.3/v0.4 모두 균등 (트래픽 총량 변화 없음). **변화는 fallback 순서**.
- 위 두 차이를 `tests/test_resolver.py::test_iterate_user_listed_rr_independent_of_priority` (n=3, user-listed ≠ priority) + `test_iterate_same_priority_preserves_user_listed_order_in_fallback` (n=3, all p=0) 가 회귀 보호.
- N 무관 — 본인 use case 의 traffic + fallback ordering 을 release 전 직접 확인 권장.

### Changed — Resolver 내부 표현
- `ProviderResolver.__init__` 에 `_providers` (user-listed) 와 `_priority_sorted` (fallback view) 두 list 보유. 이전에는 priority-sorted 만 보유 + 회전.
- `iterate()` 가 ProviderSpec identity (`is`) 로 RR-start 와 fallback 분리 — duplicate `id` 중복 방지 강제 없는 환경에서도 안전.

### Tests — `tests/test_resolver.py` 회전 가정 → start+fallback 가정 재작성
- `test_iterate_returns_full_rotation_starting_at_index` → `test_iterate_rr_start_then_priority_fallback` (semantic 명시)
- `test_iterate_user_listed_rr_independent_of_priority` 신규 — RR base = user-listed 회귀 보호 (priority 와 user-listed 가 다를 때)
- `test_iterate_same_priority_preserves_user_listed_order_in_fallback` 신규 — 동률 stable sort 회귀 보호
- `test_priority_ascending_sorts_lower_first` → `test_priority_ascending_orders_fallback_lower_first` (사실 더 정확한 이름) + 3개 호출 검증으로 확장
- `test_chain.py` 29 unit 영향 없음 (모두 default `priority=0` 동률, user-listed = priority-sorted 으로 동등)

### Fixed — AttemptRecord.phase 정확도 (외부 senior review 후속)
- `chain._failover_loop` 가 non-streaming `acall` 경로에서 모든 collect() 예외를 `phase="stream"` 으로 hardcode 기록하던 문제 수정. `ProviderTimeout(phase="first_token")` 가 raise 되면 이제 `AttemptRecord.phase = "first_token"` 로 정확히 surface — first-token timeout 이 라이브러리의 핵심 차별점인데 attempt metadata 가 이를 가리던 정확도 결함.
- 회귀 보호: `tests/test_chain.py::test_acall_first_token_timeout_records_phase_first_token_not_stream`.

### Fixed — README CI / PyPI badge stale
- CI badge 가 `CI-pending-lightgrey` placeholder 였음 (`.github/workflows/ci.yml` 은 v0.3 부터 존재). 실제 GitHub Actions workflow status badge 로 교체 (영/한 동시).
- PyPI badge: 정적 `0.4.0` → live `pypi/v/robust-llm-chain.svg`. release 진행 상황과 자동 동기화 + publish 안 된 시점에 misleading 한 정적 버전 표시 제거 (R-ext1 codex finding).

### Refactor — `AttemptPhase` Literal alias 도입 (R-ext1 codex Important)
- `AttemptRecord.phase` Literal 을 `types.AttemptPhase` alias 로 SSoT 화 + `chain._record_attempt` signature 가 `phase: AttemptPhase` 로 강화. 기존 `phase: str` widening + `# type: ignore[arg-type]` 제거. mypy 가 이제 잘못된 phase 값 (예: `"total"`) 의 `_record_attempt` 호출을 컴파일 시점에 차단.

### Validation
- 211 unit pass (3.13 + 3.12 + 3.11 venv) / mypy strict 0 / ruff 0 / format 0
- 8 integration + 1 e2e PASS (실제 API 회귀 보호 유지)

### Docs
- `README.md` / `README_KO.md` `priority=` 단일 문장 설명 → **두 역할 트래픽 모델 표** (RR / Priority + 적용 시점) + `[A,B,C]` 회귀 예시 추가.
- `README.md` / `README_KO.md` Status 섹션에 **v0.3.x → v0.4.0 upgrade warning callout** 추가 — silent fallback-order shift 위험 가시화 (v0.2 → v0.3 priority swap callout 옆에 누적 표시).
- `ARCHITECTURE.md` §3.1 lifecycle 다이어그램 step 4 코멘트: "priority-sorted rotation" → "RR start (over user-listed order) + priority-sorted fallback".
- `src/robust_llm_chain/resolver.py` module + class + method docstring 전면 재작성 — 두 역할 분리 + cycle 예시 명시.
- `src/robust_llm_chain/chain.py` module docstring 회전 표현 정정.

## [0.3.1] - 2026-04-30

### Changed — Python 3.11 / 3.12 지원 추가 (additive, non-breaking)
- `requires-python` 을 `>=3.13` → `>=3.11` 로 완화. 2026 년 enterprise / cloud 환경에서 가장 널리 배포된 3.11 + 3.12 사용자가 추가로 이용 가능 (LangChain 라이브러리들도 대부분 `>=3.10`).
- `pyproject.toml` classifiers 에 `Programming Language :: Python :: 3.11` / `3.12` 추가.
- `[tool.ruff] target-version` `py313` → `py311`, `[tool.mypy] python_version` `3.13` → `3.11` (compiler 가 3.11+ 호환 가능 코드만 emit / verify 하도록).

### Refactor — PEP 695 `type X = ...` → `TypeAlias` annotation (PEP 613)
- `src/robust_llm_chain/types.py:24` `RobustChainInput` + `src/robust_llm_chain/chain.py:57` `_TryFirstChunkResult` 두 alias 를 PEP 695 `type` 키워드 (3.12+) 에서 `TypeAlias` annotation 형태 (3.10+) 로 변환. 의미 동등 변환 — 타입 검사기 동작 동일, 런타임 도입 비용 미미. `tests/test_public_api.py::test_robust_chain_input_alias_importable_from_root` 의 PEP 695 specific `__value__` attribute 검사를 annotation form 에 맞게 약화 (functional 검증으로 대체).

### Validation
- 207 unit pass (3.13 + 3.12 + 3.11 venv) / mypy strict 0 / ruff 0 / format 0
- 8 integration + 1 e2e PASS (실제 4-provider API 회귀 보호 유지)
- 3.11.15 로컬 검증 추가 (`uv python install 3.11` + venv full unit suite)

### Docs — PyPI long_description 호환 (R6 codex finding)
- `README.md` 의 모든 relative link (`LICENSE`, `*_KO.md`, `SECURITY.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `examples/builder.py`) 를 absolute `https://github.com/jw1222/robust-llm-chain/blob/main/...` URL 로 변환. PyPI long_description 으로 이 README 가 그대로 노출되는데 PyPI 페이지에서 relative link 는 404. R6 codex 가 BLOCKER 로 식별 + in-place fix.
- `README_KO.md` 동일 처리 — 일관성 + 추후 PyPI/외부 도구가 KO 도 노출할 가능성 대비.

### Docs — drift 정리 + As-Is + upgrade warning (R5 review 반영)
- `README.md` / `README_KO.md` Status 섹션: "v0.1 is in active development / Python 3.13 only" → "v0.3.x in pre-1.0 active development / CI matrix Python 3.11 / 3.12 / 3.13"
- `README.md` / `README_KO.md` 본문에 남아있던 6건의 "v0.1 production combo" / "Active in v0.1" / "not implemented in v0.1" / "v0.1: Memcached, v0.2: Redis" 잔재 정리 (R5 simplify finding) — 영/한 동시
- `README.md` / `README_KO.md` Status 섹션에 **As-Is 명시 추가**: "no support guarantee, no SLA, fork it if it doesn't work for you" (PyPI 노출 전 사용자 기대치 정렬)
- `README.md` / `README_KO.md` Status 섹션에 **v0.2.x → v0.3.x upgrade warning callout** 추가: priority semantic 반전 + builder API 통합 BREAKING 두 가지가 PyPI long_description 에도 노출되도록 (R5 codex finding — `pip install --upgrade` 시 silent traffic shift 위험 가시화)
- `docs/policies.md` §5.3 Python 매트릭스 표 갱신 (v0.1 ~ v0.3.0 history + v0.3.1+ 현재 + v1.0 추가 검토)
- `CONTRIBUTING.md` / `CONTRIBUTING_KO.md` Environment setup: `uv run --python 3.11 ...` 후 `.venv` 재생성 시 dev tool 빠질 수 있다는 caveat + `uv sync --all-extras --python ...` 재실행 안내 추가

## [0.3.0] - 2026-04-29

### Changed (BREAKING) — `priority=` semantic 반전 (lower = preferred)

`ProviderResolver` 의 정렬 방향을 descending → ascending 으로 반전. 이제 **낮은 `priority` 값이 먼저 시도** — DNS MX records, cron priority, Linux `nice`, 인프라/큐 분야의 거의 모든 표준 관행과 일치. v0.2.x 의 desc 정렬은 사용자 mental model 과 영구적으로 어긋나는 trap 이라 (`priority=0=primary` 로 주석 달아도 실제 동작은 반대) sub-day-old release 시점에 정정.

**왜 이제야**: codex review (R5) 발견 — README quickstart 의 `priority=0 # primary` / `priority=1 # fallback` 라벨이 `resolver.py:31` 의 `sorted(..., key=lambda p: -p.priority)` 와 정반대로 동작. 첫 사용자가 README 그대로 복붙하면 의도와 거꾸로 traffic 흐름. doc-only fix (라벨만 swap) 보다 semantic-fix (코드를 사용자 직관에 맞춤) 가 영구적 mental-model 부담 0 으로 만듦.

**마이그레이션**:
- v0.2.x 에서 `priority=10` (primary) / `priority=0` (fallback) 식으로 *큰 값 = primary* 로 썼다면 값을 swap → `priority=0` (primary) / `priority=10` (fallback).
- v0.2.x README 예시를 그대로 따라 `priority=0` 을 primary 의도로 썼던 사용자는 실제로는 *fallback-first* 로 동작하던 trap 에 걸려 있었음 — v0.3 업그레이드 시 코드는 그대로지만 트래픽이 비로소 README 가 약속한 분포로 흐름. **traffic mix 가 의미 있는 production 이라면 monitoring 필요.**

### Changed (BREAKING) — Builder API 단일화

`RobustChain.builder()` 의 4 typed `add_*` 메서드를 `add_provider(type=...)` + `add_bedrock(...)` 두 개로 통합하고, env 읽기를 builder 책임에서 호출자 책임으로 이양. 사용자 dogfooding 피드백 ("env_var 가 모호함 — 어디서 할당하느냐의 문제이지 builder 가 알 일이 아니다") 즉시 반영.

**제거된 메서드**: `add_anthropic` / `add_openai` / `add_openrouter` (Anthropic / OpenAI / OpenRouter 의 시그니처가 env_var default 만 다른 거의 동일한 복붙 — `Literal["anthropic","openai","openrouter"]` 한 글자 분기로 통합 가능). `add_bedrock` 은 region + 2 credential 의 비대칭 구조라 단독 메서드로 유지.

**제거된 kwargs**: `env_var=` (single-key), `aws_access_key_env=` / `aws_secret_env=` (Bedrock). builder 가 더 이상 `os.environ` 을 직접 읽지 않음 — 호출자가 `os.environ["..."]` / vault.get() / Secrets Manager 호출로 값을 만들어 `api_key=` 또는 `aws_access_key_id=` / `aws_secret_access_key=` 에 직접 전달.

**왜**:
1. `env_var=` 가 "어디서 가져오는가" (source) 와 "값 자체" (value) 를 한 kwarg 에 섞어 모호. `api_key=` 단일화로 source 는 호출자, value 는 builder 라는 책임 분리가 명확해짐.
2. secrets manager / Vault / hardcoded test fixture 등 env 외 source 가 first-class — 더 이상 "env_var 라는 이름의 default 가 있는데 우회하려면 api_key=" 같은 escape-hatch 설명 불필요.
3. 4 typed 메서드 (60+ LOC 복붙) → 2 메서드 (~30 LOC) 로 surface 감소, 신규 single-key provider (Cohere / Mistral / …) 추가 시 `Literal` 한 글자 추가만으로 가능.

(두 BREAKING 모두 v0.2.0 ship 직후의 sub-day-old 타이밍을 활용 — 마이그레이션 비용이 가장 낮은 시점에 한 PR 으로 묶어 처리.)

**마이그레이션** (before → after):

```python
# Before (v0.2.0)
RobustChain.builder().add_anthropic(model="m").build()                       # env default
RobustChain.builder().add_anthropic(model="m", env_var="ANTHROPIC_KEY_2").build()
RobustChain.builder().add_anthropic(model="m", api_key="sk-...").build()
RobustChain.builder().add_bedrock(model="m", region="us-east-1").build()     # AWS env default
RobustChain.builder().add_bedrock(
    model="m", region="us-east-1",
    aws_access_key_env="AWS_KEY_EAST", aws_secret_env="AWS_SECRET_EAST",
).build()

# After (v0.3.0) — credential 은 모두 값으로
import os
RobustChain.builder().add_provider(
    type="anthropic", model="m", api_key=os.environ["ANTHROPIC_API_KEY"],
).build()
RobustChain.builder().add_provider(
    type="anthropic", model="m", api_key=os.environ["ANTHROPIC_KEY_2"],
).build()
RobustChain.builder().add_provider(
    type="anthropic", model="m", api_key="sk-...",
).build()
RobustChain.builder().add_bedrock(
    model="m", region="us-east-1",
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
).build()
RobustChain.builder().add_bedrock(
    model="m", region="us-east-1",
    aws_access_key_id=os.environ["AWS_KEY_EAST"],
    aws_secret_access_key=os.environ["AWS_SECRET_EAST"],
).build()
```

**영향 범위**: `RobustChain.from_env()` / 명시 `RobustChain(providers=[ProviderSpec(...)])` 두 path 는 무영향 — 변경은 builder API 안에서만. 모든 docs (README / README_KO Quickstart / "Provider configuration" matrix / examples/quickstart.py / examples/builder.py) 갱신, builder 모듈 docstring 재작성, 13 builder unit test 새 API 로 재작성 (env monkeypatch 패턴 → 직접 값 전달).

**`SingleKeyProviderType`** (`Literal["anthropic","openai","openrouter"]`) 가 builder 모듈에서 export — 외부 코드가 type 을 좁힐 때 사용 가능.

### Removed (post-v0.2.0)
- `examples/advanced.py` — `examples/builder.py` (v0.2.0) 와 같은 4 시나리오를 explicit `ProviderSpec` list 로 표현했던 예제. v0.2.0 에서 builder 가 권장 path 가 됐고 두 example 의 시나리오가 100% 중복이라 maintenance 부담만 ↑ (한 모델 ID 변경 시 두 file 수정). 사용자 명료성 + DRY 측면에서 builder.py 만 canonical 로 유지. explicit `providers=[ProviderSpec(...)]` path 가 필요한 경우 (config loader / orchestrator) README "Advanced usage" 의 inline 코드 블록이 reference 역할.
- `ProviderResolver.next()` — production code path 가 모두 `iterate()` 로 이전됐고 (concurrent failover 결함 수정의 결과) test 외 호출자가 0건. 동일 개념의 두 API surface 가 future contributor 에게 footgun ("어느 쪽을 써야 하는가?") 이라 단일화. 4 resolver 단위 테스트도 `iterate()` 기반으로 재작성.

### Added (post-R3 — CODING_STYLE compliance audit)
- `RobustChainBuilder` + `SingleKeyProviderType` 가 패키지 root 에서 import 가능 (`from robust_llm_chain import RobustChainBuilder, SingleKeyProviderType`). v0.3.0 의 BREAKING 자체가 builder API 중심인데 `from robust_llm_chain.builder import ...` 만 가능했음 (CODING_STYLE §12 위반). `ARCHITECTURE.md` §6.1 표 + `tests/test_public_api.py` 회귀 테스트도 함께 갱신.

### Style — `from __future__ import annotations` 제거 (CODING_STYLE §16 금지 항목)
- `src/robust_llm_chain/builder.py` (v0.3 신규 도입), `_security.py`, `cost.py` (사전부터 잠복) 의 `from __future__ import annotations` 제거. Python 3.13+ 는 PEP 695 alias / quoted forward ref 로 해결되므로 이 import 가 dead code 였음. `builder.py` 의 `RobustChain` 반환 타입은 quote (`"RobustChain"`) 로 처리.

### Fixed — concurrent acall failover skipping providers
`_failover_loop` / `_astream_with_failover` 가 매 retry 마다 `resolver.next()` 를 호출했음 → 글로벌 backend 인덱스가 단조 증가하므로 **두 acall 이 동시에 실행되면 서로의 인덱스를 소비해 한 호출이 같은 provider 를 재시도하면서 다른 provider 는 건너뛸 수 있음** (codex R1 발견, v0.2 부터 잠복). 수정: `ProviderResolver.iterate()` 신설 — 한 acall 당 backend 를 정확히 한 번만 tick 하고, sorted 리스트의 시작 위치를 결정한 뒤 wrap-around 로 모든 provider 를 정확히 한 번씩 반환. chain 의 두 failover 루프가 이를 사용 → "한 호출 안에서 각 provider 를 priority 순으로 정확히 한 번 시도" 의 contract 가 동시성 하에서도 보장됨. `iterate()` 자체에 회귀 테스트 (priority-sorted rotation 3건 + concurrent `asyncio.gather` 시나리오) + chain-level 3-provider failover end-to-end 테스트 (codex R2 의 coverage gap 보강 — primary fail / secondary succeed / tertiary unattempted) 포함.

### Future backlog (post-v0.2.0 — Codex / quality round 누적 권고, 모두 의도된 미룸)
- `to_safe_dict()` helper — `asdict(ChainResult)` footgun 의 안전한 직렬화 경로 (Codex R2/R3/R4 강조).
- 명시적 `__copy__` / `__deepcopy__` — 현 `__getstate__` 동작 (credential drop) 으로 안전하나 SECURITY.md §1 명시만으로 충분.
- `_KEY_PATTERNS` 에 LangSmith service token / AWS STS / 추가 prefix 보강 (현재 best-effort qualifier 명시).
- sdist `.gitignore` exclude — hatchling 표준 옵션 차단 안 됨 (`force-exclude` / hatch plugin 으로 처리).
- adapter base class 추출 — 5번째 adapter 시점.
- richer ProviderSpec credential object 분리 — Codex challenge.
- stream lifecycle object 추가 분리 — Codex challenge.
- `compute_cost(pricing, usage)` signature narrowing — Codex Review R2 5min-patch (현재 `(model_spec, usage)` 가 호출처 편의 우선).
- `env_api_key_credentials` public 노출 재검토 — Codex Review R2 (현재 외부 contributor 의 custom adapter 편의로 `__all__` 등록).
- mixed-currency 비용 누적 정책 — Codex Review R2 (현재 LHS currency 채택, orchestrator 가 single-currency 가정).
- `ProviderModelCreationFailed` 정의 vs raise 미사용 cleanup — Codex Q4 (minor dead code).
- `_V02_PLACEHOLDER_TYPES` 의 redis 분류 — backend concept 인데 provider type 으로 분류, v0.2 에서 backend extra 활성 시 재고.

## [0.2.0] - 2026-04-29

### Added
- **`RobustChain.builder()` — fluent provider configuration (third path)** — `RobustChain.builder().add_anthropic(model="...").add_openrouter(model="...").build()` 패턴. 두 기존 path (`from_env` dict-based / `providers=[...]` list-based) 의 capability split (multi-key / multi-region 표현) 을 동일 chained API 로 합치는 중간 layer. additive — 기존 path 모두 유지. credential resolution 은 `add_*` 별 default `env_var` (configurable) **또는** explicit `api_key=` (env 없어도 OK), 누락 시 `KeyError` fail-fast (silent skip 아님 — `from_env` 의 함정 반대). auto-id (`anthropic-1` / `anthropic-2`) 로 multi-key 자동 unique. `src/robust_llm_chain/builder.py` 신규 모듈, `RobustChain.builder()` classmethod, +13 RED→GREEN 단위 테스트. **사용자 dogfooding 발견 (두 path 헷갈림 → 즉시 구현)**. README "Quickstart" 도 builder 패턴으로 변경 (가장 간결). README "Provider configuration: three paths" 섹션 + decision tree 갱신.
- **`examples/builder.py`** — runnable scripts for 4 production patterns via builder API (`multikey` / `3way` / `xvendor` / `multiregion`). `examples/advanced.py` (explicit ProviderSpec list) 와 동일 시나리오, builder 로 표현.
- **`examples/quickstart.py` 갱신** — README quickstart 와 byte-identical: builder 패턴으로 변경 (이전: explicit ProviderSpec list).
- **`examples/advanced.py`** — runnable scripts for 4 production patterns: `multikey` (두 Anthropic 키 round-robin), `3way` (Anthropic + Bedrock + OpenRouter 3-way Claude failover), `xvendor` (Claude → GPT cross-vendor cross-model), `multiregion` (Bedrock east + west). README "Advanced usage" 섹션이 이제 코드 + 실행 가능한 example 모두 가리킴. v0.1.0 GitHub release 후 사용자 질문 ("multi-key 샘플은?" + "model id 는 사용자가 넣는가?" → yes, 의도된 디자인) 반영.

### Changed
- **`examples/quickstart.py` + README "Quickstart" — 명시 ProviderSpec list 로 변경**: 이전 `from_env(model_ids={"anthropic": "...", "openrouter": "anthropic/..."})` 패턴이 dict key (provider type) 와 value 안 vendor prefix (`anthropic/...`) 모두 "anthropic" 등장으로 학습 곡선 헷갈림 발생 (사용자 catch). 명시 `ProviderSpec(id="anthropic-direct", type="anthropic", model=ModelSpec(model_id="..."), api_key=..., priority=0)` 로 변경 — `id` (사용자 label) / `type` (어댑터) / `model.model_id` (vendor 식별자) 가 분리되어 각 역할 명확. `examples/advanced.py` 와 학습 곡선 일관. `from_env()` 는 README 의 별도 "Shortcut" callout 으로 분리 (의도/한계 명시). README 30-second → "Quickstart" 로 제목 변경 (verbose 해진 만큼 약속도 정직하게).
- **README "Anatomy of a result" + "Logging" 섹션 신설**: 사용자 catch ("어떤 정보가 output 으로 나오는지? log 는 어디에 기록되는지?"). `ChainResult` 8 필드 표 + happy path sample (single provider 성공 시 `output` / `usage` / `provider_used.id` / `attempts` 실제 값) + failover path sample (primary throttle 시 `attempts` 가 OverloadedError 와 fallback 모두 기록) + `chain.last_result` (contextvars-scoped) / `total_token_usage` / `total_cost` aggregate 명시. Logging 섹션은 logger 이름 (`robust_llm_chain.chain` / `robust_llm_chain.observability.langsmith`) + structured `extra` field (event / run_id / error_type 등) + "NOT logged by design" (prompt/response/credential 0 logging — SECURITY hardening #3). ARCHITECTURE.md §4 ChainResult 영역에 cross-ref 한 줄 추가.
- **한국어 번역 5 파일 추가** (root): `README_KO.md` (458줄) / `ARCHITECTURE_KO.md` (477줄) / `CONTRIBUTING_KO.md` (162줄) / `SECURITY_KO.md` (87줄) / `CODE_OF_CONDUCT_KO.md` (107줄, Contributor Covenant v2.1 [공식 한국어 번역](https://www.contributor-covenant.org/ko/version/2/1/code_of_conduct/) 어휘 차용). 영어 원본이 정본 (translation header 명시), markdown 구조 / 표 / 코드블록 / 식별자 1:1 보존, 자연어 본문만 한국어 (격식 평어체 + 정착된 음역: 폴백/페일오버/스로틀/라운드 로빈/프로덕션). README 상단에 5개 한글 문서 링크 callout 추가. `pyproject.toml [tool.hatch.build.targets.sdist].include` 에 5개 추가 — sdist 사용자도 한글 문서 접근 가능. 사용자 요청 ("**_KO.md 한글파일이 있으면 좋겠어").


## [0.1.0] - 2026-04-29

### Added — v0.1 scope 확장 (Round 0 결정 변경)
- **OpenAI 어댑터** (`adapters/openai.py`): `ChatOpenAI` (base_url 미설정 → OpenAI 본 endpoint), lazy `langchain_openai` import + `default_factory(OPENAI_API_KEY)` 동작 보장. 10 RED → GREEN.
- **Bedrock 어댑터** (`adapters/bedrock.py`): `ChatBedrockConverse` (Converse API), `ProviderSpec.region` 전달, AWS credentials 누락 시 boto3 default chain (env / IAM role / `~/.aws/credentials`) 위임. multi-region (east + west) 패턴 검증. 12 RED → GREEN.
- **`from_env`** 활성 type 확장: `anthropic` / `openrouter` / `openai` / `bedrock` 모두 지원. Bedrock 은 세 AWS env (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_REGION`) 모두 있을 때만 활성, 부분 누락 시 silent skip.
- **다중 키 / 다중 region 등록 회귀 보호**: 같은 `type` 에 다른 `id` 로 여러 ProviderSpec 등록 가능 (이전부터 코드 차원 가능했으나 README 만 보고는 "type 별 1개" 처럼 보였음 → 회귀 테스트 + Advanced usage 패턴 명시).
- **`pyproject.toml` extras 정리**: `openai` / `bedrock` 활성, `all` 에 `langchain-aws` 포함, placeholder 는 `redis` 만 남김.

### Changed
- **Round 0 결정 변경** (REVIEW_DECISIONS): "v0.1 = Anthropic + OpenRouter 만" → "v0.1 = Anthropic + OpenRouter + OpenAI + Bedrock". 사용자 결정: cross-vendor *and* cross-model failover 가 1차 라이브러리에 모두 포함되어야 한다는 정신.
- README: extras 표 / env 표 / "Three things" / "Who is this for" / Advanced usage 갱신. multi-key, multi-region (Bedrock east/west), 3-way Claude (Anthropic + Bedrock + OpenRouter), Claude → GPT cross-vendor cross-model 패턴 추가.
- `.env.example`: OpenAI / Bedrock 의 v0.2 라벨 제거.

### Security
- **`ProviderSpec` credential 마스킹 강화** (`types.py`): credential 3 필드 (`api_key` / `aws_access_key_id` / `aws_secret_access_key`) 에 `compare=False` 추가 — pytest assertion introspection 시 credential 평문이 diff 출력에 노출되던 경로 차단. `__getstate__` / `__setstate__` 오버라이드로 `pickle.dumps(spec)` 가 credential 을 직렬화하지 않도록 함 (분산 task queue / 캐시 / multiprocess 전송 시 누출 방지). `dataclasses.asdict()` / `astuple()` 은 dataclass 표준 동작상 모든 필드를 무조건 traverse 하므로 credential 노출 — `SECURITY.md` #1 에 미보장 경로로 명시 + 안전한 사용법 (`repr(spec)` 권장) 가이드 추가.
- **SECURITY.md hardening 정확성 보강**: #1 보장 경로 / 미보장 경로 표 형식으로 명확화. #2 `_security.sanitize_message` 패턴이 best-effort 임을 명시 (LangSmith service token / AWS STS / 광범위 base64 false positive 한계).
- **`copy.copy` / `copy.deepcopy` 동작 명시**: `__getstate__` / `__setstate__` 오버라이드가 Python copy protocol 에도 동일 적용 → `copy.deepcopy(spec)` 도 credential 을 잃음 (None). 사용자가 spec 을 런타임 재사용 목적으로 복사하면 인증 실패 가능 — `SECURITY.md` #1 에 "spec 재사용 목적이면 copy 가 아니라 새 ProviderSpec 생성" 가이드 추가.
- **`asdict(ChainResult)` footgun 명시**: `ChainResult.provider_used` 가 `ProviderSpec` 을 보유하므로 `asdict(result)` 가 nested credential 평문 노출. `SECURITY.md` #1 에 직접 언급 추가 (이전엔 embedded ProviderSpec 일반화로만 언급).
- **`ARCHITECTURE.md §4` Credential masking 갱신**: layer #5 (`compare=False`) + layer #6 (`__getstate__` / `__setstate__`) 추가, "every channel" → "most channels" + asdict 미보장 명시 + `SECURITY.md §1` cross-ref.
- **`pyproject.toml` sdist include 보강**: `SECURITY.md` / `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` 추가 — sdist-only 사용자도 보안 보장표 / TDD 룰 / CoC 접근 가능 (Round 3 종합 리뷰 + CSO 합의 발견).
- **`_security.py` docstring**: `_KEY_PATTERNS` 가 best-effort 임을 코드 reader 가 즉시 인지하도록 한 줄 명시 + `SECURITY.md §2` cross-ref.
- **`observability/langsmith.py` 의 `cleanup_run` credential 누출 차단**: provider SDK 가 401/403 응답에서 api_key 를 echo back 하는 경우 raw error 가 LangSmith dashboard 의 `run.error` 필드에 그대로 노출되던 경로 차단. `_update_run` 이 `sanitize_message(str(error))` 거치도록 수정 (기존 `str(error)` 직접 전달). RED→GREEN 회귀 테스트 추가 (`test_cleanup_run_sanitizes_credential_in_error_before_sending`). Codex Round 4 발견.
- **`SECURITY.md §1` 의 `repr(result)` 권장 정정**: 이전 문구가 "use `repr(spec)` / `repr(result)`" 였으나 `ChainResult` 는 default dataclass repr 라 `input` (prompt) / `output` (response) 평문 노출 — hardening #3 ("library never logs prompt/response") 와 모순. `repr(spec)` 만 안전하다는 명확화 + 사용자가 ChainResult 를 직렬화할 때 명시적 필드 추출 (provider id / elapsed_ms / usage / attempts) 권장으로 수정. Codex Round 4 발견.
- **`pyproject.toml` sdist `.gitignore` 제외 시도 (v0.2 미룸)**: hatchling 기본 동작이 sdist 에 `.gitignore` 를 자동 포함하며 표준 `exclude` 옵션으로 차단되지 않음 (Round 4 검증). `.gitignore` 가 노출하는 정보는 일반 glob + 사적 파일명 1개 (`docs/start/PRIVATE_NOTES.md`) 로 minor information leak. v0.2 에서 `force-exclude` 또는 hatch plugin 으로 처리. pyproject.toml 에 NOTE 주석 추가. Codex Round 4 발견 L3.

### Refactor / Quality (v0.1.0 ship 직전 micro-refactoring)
- **DRY — `_accumulate_usage` 중복 제거**: chain.py 와 stream.py 양쪽에 12줄 동일 함수가 정의되어 있어 chain.py 가 stream._accumulate_usage 를 import 하도록 통합 (CODING_STYLE §1.7 — 의미 동일성 강한 결합).
- **DRY — `DEFAULT_MAX_OUTPUT_TOKENS` 4중복 제거**: 4개 어댑터 (anthropic / openrouter / openai / bedrock) 각각에 동일 상수 `_DEFAULT_MAX_OUTPUT_TOKENS = 4096` 가 있던 것을 `adapters/__init__.py` 에 public `DEFAULT_MAX_OUTPUT_TOKENS` 로 승격. `__all__` 에 등록 (단일 편집점, 4-strike DRY 명확).
- **DRY — `_ensure_builtin_adapters_registered` 단순화**: chain.py 의 4중 `if X not in registry: register_adapter(X())` 패턴을 `_BUILTIN_ADAPTERS` tuple + loop 로 단순화.
- **`pyproject.toml` `redis` placeholder extra 제거**: PyPI 사용자에게 `pip install robust-llm-chain[redis]` 가 보이지만 실제로 redis 백엔드 코드는 v0.2 까지 미구현 — placeholder 가 misleading 이라 제거. `_V02_PLACEHOLDER_TYPES` 의 `ProviderInactive` 메시지도 "installed but inactive" → "reserved for v0.2" 로 정정. Codex Round (quality) 발견.
- **`from_env` unknown provider type 시 WARN log**: 이전엔 typo (`antrophic`) 같은 unknown type 을 silent skip 하다가 모든 provider 가 빠지면 `NoProvidersConfigured` raise — 사용자가 원인 모름. `robust_llm_chain.chain` 모듈 logger 에 WARN 출력 (active types 명시 + "Possible typo?") 으로 관찰성 강화. RED→GREEN 회귀 테스트 추가. Codex Round (quality) 발견.
- **`compute_cost` → `cost.py` 분리** (SRP — single responsibility): chain.py 의 `_compute_cost` instance 메서드가 `self` 미사용 순수 함수였음 → `src/robust_llm_chain/cost.py` 로 분리. chain.py 슬림 (29줄 감소), cost 단독 단위 테스트 5개 추가 (`tests/test_cost.py`), 미래 확장 (currency 변환 / 동적 pricing 조회) 격리. 외부 사용자가 `from robust_llm_chain.cost import compute_cost` 로 직접 import 가능 (root `__all__` 미추가, 보수적). Codex Round (quality) 1시간 권고.
- **`env_api_key_credentials` helper 공통화**: 3 adapter (anthropic / openrouter / openai) 의 `credentials_present` 가 100% 동일 패턴 (env.get(KEY) → {'api_key': value} | None). `adapters/__init__.py` 에 `env_api_key_credentials(env, env_var)` 추가, 3 adapter 가 사용. Bedrock 만 multi-field detector 라 별개. 외부 contributor 가 새 single-key adapter 만들 때 활용 가능 (`__all__` 등록). Codex Round (quality) 1시간 권고.
- **`CostEstimate.__add__` operator + `_update_totals` 슬림** (`types.py` +12줄, `chain.py` -9줄): `CostEstimate` 에 field-wise sum 의 `__add__` dunder 추가 (LHS currency 채택, mixed-currency 는 caller 책임 — orchestrator 는 single-currency 가정). `chain.py` 의 `_update_totals` 가 6-field manual sum boilerplate 대신 operator 사용. `TokenUsage.__add__` / `__iadd__` 와 일관된 orthogonal operator 패턴 (cohesion 향상). /simplify R2 + Codex Review R2 독립 합의 발견.

### Test coverage 보강 (93% → 95%)
- **Protocol body `pragma: no cover`**: `IndexBackend` (3) + `ProviderAdapter` (2) + `MemcacheClient` (5) Protocol 메서드의 `...` body 10곳에 `# pragma: no cover` 추가 — Protocol 정의일 뿐 실행되지 않는 코드라 정직한 분류 (CODING_STYLE §10).
- **`tests/test_security.py` 신규** (+7 tests): `sanitize_message` None / truncate / 다중 prefix 매칭 / mask 후 truncate 분기. `_security.py` coverage 78% → 100%.
- **`tests/test_observability.py` 추가** (+1 test): `_update_run` 의 generic `Exception` 분기 (LangSmith outage / SDK ImportError 시 WARN 로그 + caller 미차단). `langsmith.py` coverage 96% → 100%.
- **`tests/test_memcached_backend.py` 추가** (+3 tests): `BackendUnavailable` fail-closed (`OSError` on `incr` / `reset`, `add` 실패 후 retry-incr 도 `None` 인 race 케이스). `memcached.py` coverage 77% → 98%.
- **결과**: 180 → **191 unit pass**, coverage 93% → **95%** (DoD §3.2 의 ≥80% 를 크게 상회).

### Documentation
- **`ARCHITECTURE.md` 를 project root 로 승격** — 외부 contributor 친화적. 모듈 구조 / 의존 그래프 / 호출 lifecycle / 데이터 모델 / 에러 흐름 / public surface / 확장점 (custom ProviderAdapter / IndexBackend / fail-closed semantics) 정리. README 의 새 "Architecture" 섹션에서 링크. `pyproject.toml [tool.hatch.build.targets.sdist]` 에 포함되어 PyPI sdist 와 함께 배포.
- **OSS 표준 문서 정리**: CONTRIBUTING / SECURITY / CODE_OF_CONDUCT (root) + `.github/ISSUE_TEMPLATE/` (bug_report + feature_request) + `.github/PULL_REQUEST_TEMPLATE.md` 추가. contributor 친화적 표준 갖춤.
- **`adapters/__init__.py` docstring**: built-in 4 provider (anthropic / openrouter / openai / bedrock) 모두 명시 (Round 0 결정 변경 후 갱신 누락 보정).
- **`pyproject.toml` PyPI metadata 보정**: keywords 에 `openai` / `bedrock` 추가, classifier `Development Status :: 3 - Alpha` → `4 - Beta` (version `0.1.0` 이 non-prerelease 인 점과 일관).

### Added — Phase 4 (T1~T13) 완료
- **공개 데이터 모델** (`types.py`): `RobustChainInput` PEP 695 alias, `ProviderSpec` (slots + `__repr__` 마스킹), `ModelSpec`, `PricingSpec`, `TokenUsage` (`__add__`/`__iadd__`), `CostEstimate`, `ChainResult` (mutable, astream lifecycle), `AttemptRecord`, `TimeoutConfig`.
- **에러 계층** (`errors.py`): `RobustChainError` 베이스 + 10 전문화 클래스, `is_fallback_eligible` 3단계 분류 (typed → SDK class → keyword).
- **백엔드** (`backends/`): `IndexBackend` Protocol, `LocalBackend` (asyncio.Lock 100회 동시성 검증), `MemcachedBackend` (`MemcacheClient` Protocol + `add` seed + `incr` 원자성, `BackendUnavailable` fail-closed).
- **어댑터** (`adapters/`): `ProviderAdapter` Protocol + registry, `AnthropicAdapter` (lazy `langchain_anthropic` import + `default_factory(env)` 동작 보장), `OpenRouterAdapter` (`ChatOpenAI(base_url=openrouter)`).
- **스트리밍** (`stream.py`): `StreamExecutor` 3-phase — first_token wait → cumulative per-provider deadline → bounded `aclose()` cleanup.
- **리졸버** (`resolver.py`): `ProviderResolver` 라운드로빈 + priority 정렬 + 빈 providers `NoProvidersConfigured`.
- **체인** (`chain.py`): `RobustChain` Hybrid API — `ainvoke`/`astream` (Runnable 표준) + `acall` (`ChainResult` 직접 반환), `last_result` contextvars 격리, `total_token_usage`/`total_cost` `asyncio.Lock` 누적, `from_env(model_ids)` 자동 ProviderSpec 구성, astream pre/post-commit 분리 (silent fallback / `StreamInterrupted`).
- **관측성** (`observability/langsmith.py`): `cleanup_run` + `Semaphore(50)` backpressure (drop+WARN 1회 rate-limited) + 5초 timeout, `LANGSMITH_API_KEY` 미설정 silent.
- **테스트 유틸** (`testing/`): `FakeAdapter` (text/exception/chunks/delay/usage/chunks_exception 시나리오 + bind kwargs capture), `install_fake_adapter()` 명시 호출만 등록.
- **테스트 커버리지**: 143 unit tests pass (mypy strict 0 / ruff 0 / format 통과 / coverage 92%). Integration (`tests/integration/`) + E2E (`tests/e2e/`) 시나리오는 키 없으면 자동 skip.

### Fixed
- `AnthropicAdapter`: `spec.api_key=None` 시 빈 `SecretStr` 명시 전달 → `default_factory(env)` 우회되던 버그 수정. 이제 `ANTHROPIC_API_KEY` env 자동 read 정상 동작.

### Earlier — Phase 0~3 (initial scaffold)
- 초기 repo skeleton (CONCEPT v2 기반).
- `RobustChain` Hybrid API stub (Runnable + acall).
- `LocalBackend` (asyncio.Lock 기반 라운드로빈) 실구현.
- `FakeAdapter` (테스트 유틸) 실구현.
- 빌드/CI: pyproject.toml (uv/PEP 621/hatchling), `.github/workflows/ci.yml`, Makefile, `.gitignore`, `LICENSE` (MIT).
- 문서: `README.md`, `CHANGELOG.md`, `LICENSE` (internal design docs are local-only).
