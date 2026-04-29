# Contributing to robust-llm-chain

> 🇰🇷 한국어 번역. 원본은 [CONTRIBUTING.md](CONTRIBUTING.md) 참조 — 원본이 정본이며, 번역과 원본이 다를 시 원본 우선.

> 개인 규모의 OSS — 단일 메인테이너이며 외부 기여에 의존하지 않는다. 그래도 PR 과 issue 는 환영.

비자명한(non-trivial) PR 을 열기 전에 [ARCHITECTURE.md](ARCHITECTURE.md) 를 읽어라. 거기에 적힌 모듈 구조 / 호출 lifecycle / 확장 지점이 계약이며, 그것에 어긋나는 PR 은 redirect 된다.

---

## TL;DR (PR 전 5분 점검)

1. `make lint && make type && make test` 가 로컬에서 통과한다.
2. 새 코드는 **TDD 사이클** 을 따른다 — RED → GREEN → REFACTOR → COMMIT (사이클당 commit 하나).
3. Commit 메시지는 [Conventional Commits](https://www.conventionalcommits.org/) 사용 (`feat(scope): …`, `fix(scope): …`, `refactor(scope): …`).
4. 어떤 commit 파일에도 (PR description 포함) API key, AWS access key, 기타 비밀이 없어야 한다. `ProviderSpec` 의 `__repr__` 가 런타임 값은 마스킹하지만, commit 은 마스킹하지 않는다.
5. Public-API 변경 (`robust_llm_chain.__init__.__all__` 또는 문서화된 subpath 의 모든 것) 은 정렬을 위해 사전 issue 가 필요하다.

---

## 환경 설정 — uv only

이 프로젝트는 [uv](https://docs.astral.sh/uv/) 만 사용한다. poetry / pip-tools / pdm 을 도입하지 말 것.

```bash
# uv 가 없으면 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone + install (.venv 자동 생성, 모든 extras)
git clone https://github.com/jw1222/robust-llm-chain.git
cd robust-llm-chain
uv sync --all-extras

# 검증
make lint    # ruff check + ruff format --check
make type    # mypy --strict src/robust_llm_chain
make test    # pytest unit only (key 없으면 integration/e2e 자동 skip)
```

`uv.lock` 은 commit 되어 있다 — 모든 기여자가 동일한 pinned 버전을 쓴다. 의존성을 업그레이드해야 한다면 `uv lock --upgrade` 를 실행하고 PR 본문에 사유를 적어라.

---

## 기여 유형

### 1) 버그 리포트 / 기능 요청 (issue)

GitHub issue 템플릿(`.github/ISSUE_TEMPLATE/`) 을 사용. 버그 리포트에는 다음을 포함:

- 최소 재현
- 기대 동작 vs 실제 동작
- Python 버전, OS, 관여한 adapter (`anthropic` / `openrouter` / `openai` / `bedrock`)
- traceback — **자격증명 패턴은 직접 손으로 지운 뒤 붙일 것**; 본 repo 의 마스킹은 런타임 객체만 다루며 댓글창에 붙여 넣은 텍스트는 보호하지 않는다
- `LANGCHAIN_TRACING_V2` 활성화 여부

**엄격한 규칙:** API key, AWS access key, LangSmith token 을 issue, PR description, commit message 에 절대 붙이지 말 것. 그 채널들에는 자동 마스킹이 없다.

### 2) 코드 PR

#### 사전 issue 가 필요

- Public API 변경 (`robust_llm_chain.__init__` 에서 export 되는 모든 것)
- `ProviderSpec` / `ModelSpec` / `ChainResult` / 등의 새 필드
- 예외 계층 또는 `is_fallback_eligible` 분류 변경
- 새로운 core 또는 extras 의존성
- CHANGELOG 에 문서화된 v0.1 / v0.2 범위 경계를 넘는 모든 변경

#### Issue 불필요

- 버그 수정 (회귀 테스트 동반)
- 문서 오타 / 명확화
- Public API 를 바꾸지 않는 내부 리팩토링
- 추가 `FakeAdapter` 테스트 시나리오
- CI 개선

#### TDD 사이클 (강제)

새로운 기능 또는 수정된 기능 모두에 대해:

1. **RED** — 실패하는 테스트를 먼저 작성.
2. **GREEN** — 그것을 통과시키는 최소 구현 작성. 더하지 말 것.
3. **REFACTOR** — 같은 동작, 더 깨끗한 모양. 테스트 재실행.
4. **COMMIT** — 사이클당 Conventional Commits 메시지 하나.

Test-after-code (구현 먼저 후 나중에 테스트 추가) 는 거부된다. 유일한 예외는 동작 변경이 없는 순수 리팩토링 — commit body 에 명시적으로 그렇다고 적을 것.

#### Breaking-change 체크리스트

다음을 만족하면 변경은 **breaking** 이다 (CHANGELOG 에 명시; 0.x 에서 minor bump 또는 1.x+ 에서 deprecation cycle 따름):

- `robust_llm_chain.__init__.__all__` 의 어떤 것을 제거 / 이름 변경
- Public dataclass 의 필드 제거, 타입 변경, 또는 의미 변경
- Public 예외 클래스 제거 또는 부모 변경
- 인식되는 env var 의 이름 변경 또는 활성화 규칙 변경
- `is_fallback_eligible` 의 기존 예외 family 분류 변경
- Default timeout, default backend, 또는 default adapter 동작 변경
- `chain.last_result` 의 lifecycle 변경

Breaking 이 아닌 것:

- 선행 underscore 가 붙은 모든 것
- `__init__` 또는 문서화된 subpath 로 노출되지 않는 모듈 내부 변경
- Tests, CI, build 설정

### 3) 문서 PR

- 주변 언어와 맞춰라. README 는 영어; commit message 는 한국어든 영어든 모두 허용, 다만 commit 하나 안에서는 일관성 유지.
- 코드 docstring 은 영어 (Google style).
- 섹션을 cross-reference 할 때 편집 후에도 anchor 가 살아 있는지 확인.

---

## PR description 체크리스트

모든 PR 상단에 이것을 붙여라:

```markdown
## Checklist
- [ ] Aligns with ARCHITECTURE.md (module layout, call lifecycle, extension contracts)
- [ ] Prior-issue link if changing public API or scope: #...
- [ ] TDD cycle followed (RED → GREEN → REFACTOR per cycle, one commit each)
- [ ] New tests added or existing tests updated
- [ ] `make lint` passes (ruff + ruff format --check)
- [ ] `make type` passes (mypy --strict)
- [ ] `make test` passes (unit)
- [ ] CHANGELOG.md updated if user-visible
- [ ] Breaking change called out per checklist above
- [ ] No credentials or local-path leaks in diff or description
```

---

## Security

취약점 (자격증명 누출, RCE, 의존성 CVE, 등) 에 대해서는 **공개 issue 를 열지 말 것**. 비공개 보고 경로는 [SECURITY.md](SECURITY.md) 참조.

만약 자격증명을 실수로 commit 했다면, 즉시 provider 에서 키를 rotate 한 뒤 force-push 로 blob 을 떨어뜨려라. History 재작성만으로는 누출된 키를 무효화하지 못한다 — rotation 이 먼저다.

---

## 자주 나오는 질문

**Q: `chain.acall("hi", max_tokens=20)` 에서 `max_tokens` 는 모델 옵션인가, template 변수인가?**
모델 옵션이다. `acall(prompt, *, max_tokens=None, temperature=None, config=None, **template_inputs)` 가 호출 옵션을 keyword-only 로 명시화하며, `**template_inputs` 는 명시 목록에 없는 이름들만 모은다. 따라서 `max_tokens` 는 항상 모델로 라우팅되며, 절대 `ChatPromptTemplate` 변수로 가지 않는다.

**Q: `from_env` 가 `model_ids={"antrophic": "..."}` 같은 오타를 보면 어떻게 되나?**
알 수 없는 type 은 조용히 skip 된다. 활성 provider 가 0개로 끝나면 `NoProvidersConfigured` 가 raise 된다. 향후 버전에서 `model_ids` key 타입을 더 엄격하게 만들 수 있다.

**Q: gunicorn × N worker + Memcached down — chain 이 어떻게 행동하나?**
**fail-closed.** `MemcachedBackend.get_and_increment` 가 `BackendUnavailable` 을 raise 한다. 본 라이브러리는 `LocalBackend` 로 **조용히** 폴백하지 **않는다** — 그러면 worker 조율 라운드 로빈 보장이 조용히 깨지고, 여러 worker 가 동일 provider 를 두드리기 시작할 것이기 때문. 애플리케이션에서 에러를 catch 하고 명시적으로 결정 (`LocalBackend()` 로 chain 재구성, 요청 실패 처리, circuit breaker 트립, 등). 진짜 fail-open 동작이 필요하면 얇은 `FailoverBackend` wrapper 를 작성 — 예제는 [ARCHITECTURE.md §7.3](ARCHITECTURE.md#73-fail-closed-semantics-for-shared-backends).

**Q: 스트리밍이 도중에 실패하면 부분 출력은 어디서 보나?**
`StreamInterrupted` 이후, `chain.last_result` 가 부분 `output.content` 와 전체 `attempts` 리스트를 담는다. `last_result` 는 `contextvars` scope 이라, 동시 실행되는 `astream` 호출들이 서로에게 새지 않는다.

**Q: 새 provider 는 어떻게 추가하나?**
`ProviderAdapter` Protocol 을 구현 (`type` ClassVar + `build(spec)` + `credentials_present(env)` — 4줄) 하고 `register_adapter(MyAdapter())` 를 호출. 내장 adapter 들은 정확히 동일한 Protocol 을 사용한다 — [ARCHITECTURE.md §7.1](ARCHITECTURE.md#71-new-provider-adapter) 참조.

---

## License

MIT. 기여함으로써 동일 조건 하에 작업이 라이선싱되는 것에 동의한다.
