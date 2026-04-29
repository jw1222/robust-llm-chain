# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식, [Semantic Versioning](https://semver.org/) 준수.

## [Unreleased]

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
