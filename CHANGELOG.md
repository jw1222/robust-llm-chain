# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식, [Semantic Versioning](https://semver.org/) 준수.

## [Unreleased]

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

### Documentation
- **`ARCHITECTURE.md` 를 project root 로 승격** — 외부 contributor 친화적. 모듈 구조 / 의존 그래프 / 호출 lifecycle / 데이터 모델 / 에러 흐름 / public surface / 확장점 (custom ProviderAdapter / IndexBackend / fail-closed semantics) 정리. README 의 새 "Architecture" 섹션에서 링크. `pyproject.toml [tool.hatch.build.targets.sdist]` 에 포함되어 PyPI sdist 와 함께 배포.
- **OSS 표준 문서 정리**: CONTRIBUTING / SECURITY / CODE_OF_CONDUCT (root) + `.github/ISSUE_TEMPLATE/` (bug_report + feature_request) + `.github/PULL_REQUEST_TEMPLATE.md` 추가. contributor 친화적 표준 갖춤.

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
