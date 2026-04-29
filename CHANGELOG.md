# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식, [Semantic Versioning](https://semver.org/) 준수.

## [Unreleased]

### Added (post-v0.1.0 GitHub release)
- **`RobustChain.builder()` — fluent provider configuration (third path)** — `RobustChain.builder().add_anthropic(model="...").add_openrouter(model="...").build()` 패턴. 두 기존 path (`from_env` dict-based / `providers=[...]` list-based) 의 capability split (multi-key / multi-region 표현) 을 동일 chained API 로 합치는 중간 layer. additive — 기존 path 모두 유지. credential resolution 은 `add_*` 별 default `env_var` (configurable) **또는** explicit `api_key=` (env 없어도 OK), 누락 시 `KeyError` fail-fast (silent skip 아님 — `from_env` 의 함정 반대). auto-id (`anthropic-1` / `anthropic-2`) 로 multi-key 자동 unique. `src/robust_llm_chain/builder.py` 신규 모듈, `RobustChain.builder()` classmethod, +13 RED→GREEN 단위 테스트. **사용자 dogfooding 발견 (두 path 헷갈림 → 즉시 구현)**. README "Quickstart" 도 builder 패턴으로 변경 (가장 간결). README "Provider configuration: three paths" 섹션 + decision tree 갱신.
- **`examples/builder.py`** — runnable scripts for 4 production patterns via builder API (`multikey` / `3way` / `xvendor` / `multiregion`). `examples/advanced.py` (explicit ProviderSpec list) 와 동일 시나리오, builder 로 표현.
- **`examples/quickstart.py` 갱신** — README quickstart 와 byte-identical: builder 패턴으로 변경 (이전: explicit ProviderSpec list).
- **`examples/advanced.py`** — runnable scripts for 4 production patterns: `multikey` (두 Anthropic 키 round-robin), `3way` (Anthropic + Bedrock + OpenRouter 3-way Claude failover), `xvendor` (Claude → GPT cross-vendor cross-model), `multiregion` (Bedrock east + west). README "Advanced usage" 섹션이 이제 코드 + 실행 가능한 example 모두 가리킴. v0.1.0 GitHub release 후 사용자 질문 ("multi-key 샘플은?" + "model id 는 사용자가 넣는가?" → yes, 의도된 디자인) 반영.

### Changed (post-v0.1.0 GitHub release)
- **`examples/quickstart.py` + README "Quickstart" — 명시 ProviderSpec list 로 변경**: 이전 `from_env(model_ids={"anthropic": "...", "openrouter": "anthropic/..."})` 패턴이 dict key (provider type) 와 value 안 vendor prefix (`anthropic/...`) 모두 "anthropic" 등장으로 학습 곡선 헷갈림 발생 (사용자 catch). 명시 `ProviderSpec(id="anthropic-direct", type="anthropic", model=ModelSpec(model_id="..."), api_key=..., priority=0)` 로 변경 — `id` (사용자 label) / `type` (어댑터) / `model.model_id` (vendor 식별자) 가 분리되어 각 역할 명확. `examples/advanced.py` 와 학습 곡선 일관. `from_env()` 는 README 의 별도 "Shortcut" callout 으로 분리 (의도/한계 명시). README 30-second → "Quickstart" 로 제목 변경 (verbose 해진 만큼 약속도 정직하게).
- **README "Anatomy of a result" + "Logging" 섹션 신설**: 사용자 catch ("어떤 정보가 output 으로 나오는지? log 는 어디에 기록되는지?"). `ChainResult` 8 필드 표 + happy path sample (single provider 성공 시 `output` / `usage` / `provider_used.id` / `attempts` 실제 값) + failover path sample (primary throttle 시 `attempts` 가 OverloadedError 와 fallback 모두 기록) + `chain.last_result` (contextvars-scoped) / `total_token_usage` / `total_cost` aggregate 명시. Logging 섹션은 logger 이름 (`robust_llm_chain.chain` / `robust_llm_chain.observability.langsmith`) + structured `extra` field (event / run_id / error_type 등) + "NOT logged by design" (prompt/response/credential 0 logging — SECURITY hardening #3). ARCHITECTURE.md §4 ChainResult 영역에 cross-ref 한 줄 추가.
- **한국어 번역 5 파일 추가** (root): `README_KO.md` (458줄) / `ARCHITECTURE_KO.md` (477줄) / `CONTRIBUTING_KO.md` (162줄) / `SECURITY_KO.md` (87줄) / `CODE_OF_CONDUCT_KO.md` (107줄, Contributor Covenant v2.1 [공식 한국어 번역](https://www.contributor-covenant.org/ko/version/2/1/code_of_conduct/) 어휘 차용). 영어 원본이 정본 (translation header 명시), markdown 구조 / 표 / 코드블록 / 식별자 1:1 보존, 자연어 본문만 한국어 (격식 평어체 + 정착된 음역: 폴백/페일오버/스로틀/라운드 로빈/프로덕션). README 상단에 5개 한글 문서 링크 callout 추가. `pyproject.toml [tool.hatch.build.targets.sdist].include` 에 5개 추가 — sdist 사용자도 한글 문서 접근 가능. 사용자 요청 ("**_KO.md 한글파일이 있으면 좋겠어").


### v0.2 backlog (Codex / quality round 누적 권고, 모두 의도된 미룸)
- ~~**Fluent builder API**~~ → **v0.2.0 에서 구현 완료** (위 Added 섹션 참조).
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
