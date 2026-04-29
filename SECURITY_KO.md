# Security Policy

> 🇰🇷 한국어 번역. 원본은 [SECURITY.md](SECURITY.md) 참조 — 원본이 정본이며, 번역과 원본이 다를 시 원본 우선.

## 지원 버전

이 프로젝트는 1.0 이전의 활성 개발 단계이다. 최신 `0.x` 릴리즈만 보안 수정을 받는다.

| Version | Supported |
|---|---|
| Latest `0.x` | ✓ |
| Older `0.x` | ✗ — 최신으로 업그레이드 |

`1.0` 이 출시되면 지원 윈도우가 여기에 정의된다.

---

## 취약점 보고

**보안 문제에 대해 공개 GitHub issue 를 열지 마라.**

대신 **GitHub Security Advisories** (비공개) 를 사용하라:

1. <https://github.com/jw1222/robust-llm-chain/security/advisories/new> 로 이동
2. 최소 재현과 함께 취약점을 기술
3. 수신 확인을 기다림 (목표: 7일 이내)

Security Advisories 를 사용할 수 없다면, 메인테이너 이메일로 보내라 (주소는 GitHub 프로필에 명시). 가능하면 메인테이너의 공개키로 암호화하라.

### 포함할 내용

- 영향받는 버전과 플랫폼
- 재현 단계 또는 proof-of-concept
- 영향 평가 (기밀성 / 무결성 / 가용성)
- 수정안이 있다면 제안

### 기대할 수 있는 것

| Stage | Target |
|---|---|
| 수신 확인 | 7일 이내 |
| Triage + 초기 평가 | 14일 이내 |
| 수정 또는 완화 계획 | High / Critical 은 30일 이내 |
| 조율된 공개 | 통상 보고로부터 90일; 수정이 더 빨리 출시되면 그 시점 |

CHANGELOG 와 release note 에 크레딧이 주어진다 — 익명을 선호하면 그렇게 처리한다.

---

## 범위

### In scope

- 라이브러리 API 를 통한 코드 실행 / 권한 상승
- 로그, 예외 메시지, `repr()`, 또는 LangSmith trace 에서의 자격증명 노출
- `_security.sanitize_message` 마스킹 패턴 우회
- Adapter / backend 레이어의 injection 취약점
- Timeout 을 우회하는 조작된 입력에 의한 denial-of-service
- Pinned 의존성 버전 (`uv.lock`) 의 취약점

### Out of scope

- 본 라이브러리를 잘못 사용하는 사용자 코드의 취약점 (예: `result.input` 을 인증 없는 채널로 로깅)
- 상위 provider (Anthropic, OpenAI, OpenRouter, AWS) 의 취약점 — 그쪽으로 보고
- 사용자 머신에 물리적 접근이 필요한 이슈
- 무관한 도구의 self-XSS
- `# type: ignore` / 내부 심볼의 monkey-patching 으로만 재현되는 버그

---

## 라이브러리가 보장하려고 하는 hardening

이는 public 계약의 일부 — 어떤 릴리즈에서 이것이 깨지면 보고할 가치가 있는 보안 회귀이다:

1. **`ProviderSpec` 자격증명 마스킹 — 다루는 경로**: `repr(spec)` / `str(spec)` (custom `__repr__` 와 `field(repr=False)`), `vars(spec)` / `spec.__dict__` (`slots=True` 가 차단), 동등성 / 해싱 (`compare=False` 가 자격증명 필드에 — pytest assertion introspection 이 실패 diff 에 자격증명을 출력하는 것을 막음), 그리고 `pickle.dumps(spec)` (custom `__getstate__` 가 직렬화 전에 자격증명 제거). 동일한 `__getstate__` 가 `copy.copy(spec)` 와 `copy.deepcopy(spec)` 에도 사용된다 — 자격증명은 복사본에서 제거 (`None` 으로) 된다. 직렬화가 아니라 런타임 재사용을 위해 `spec` 을 복사할 의도라면, 복사 대신 자격증명을 명시적으로 넣어 새 `ProviderSpec` 을 생성하라. **다루지 않는 것** — `dataclasses.asdict(spec)` 와 `dataclasses.astuple(spec)` 는 모든 필드를 무조건 순회하여 자격증명을 평문으로 노출한다. 동일한 점이 **`dataclasses.asdict(chain_result)`** 에도 재귀적으로 적용된다: `ChainResult.provider_used` 가 `ProviderSpec` 을 들고 있기 때문에, result 에 `asdict()` 를 호출하면 중첩 dict 에 자격증명이 드러난다. `pydantic.BaseModel.model_dump()` 도 마찬가지로 내부에 임베드된 모든 `ProviderSpec` 을 노출한다. **`ProviderSpec` 을 로깅할 때는 `repr(spec)` 을 사용하라 (custom `__repr__` 가 자격증명을 마스킹).** `repr(chain_result)` 에 의존하지 마라 — `ChainResult` 는 default dataclass repr 를 사용하며, 그것은 `input` (prompt) 과 `output` (response) 를 평문으로 노출한다. Hardening #3 가 이것을 애플리케이션의 책임으로 만든다: 결과 전체를 dump 하지 말고 영속화하고 싶은 특정 필드 (`result.provider_used.id`, `result.elapsed_ms`, `result.usage`, `result.attempts`) 를 추출하라. `dataclasses.asdict(...)` 를 두 타입 어디에도 절대 사용하지 말 것.
2. **`AttemptRecord.error_message`** 는 `_security.sanitize_message` 로 정화된다 — provider API key prefix, AWS access key id 형식, LangSmith personal token 형식 (정확한 정규식은 `src/robust_llm_chain/_security.py` 의 `_KEY_PATTERNS` 참조) 이 `***` 로 치환된 뒤 문자열은 200자로 잘린다. Best-effort 한정: 덜 흔한 token 형식 (LangSmith 서비스 토큰, AWS STS / 임시 자격증명) 과 provider 별 변종은 현재 패턴 집합에 포함되지 않으며, catch-all 40자 base64 패턴은 자격증명이 아닌 문자열을 마스킹할 수 있다 (false positive). 마스킹을 빠져나가는 실제 자격증명 prefix 를 발견하면 issue 를 열어달라.
3. **라이브러리 자체는 prompt 또는 response 텍스트를 절대 로깅하지 않는다.** `ChainResult.input` / `ChainResult.output` 의 audit 로깅은 애플리케이션의 책임이다 — 라이브러리는 WARN/ERROR 레벨에서 구조화된 메타데이터 (provider id, elapsed_ms, error type) 만 발생시킨다.
4. **`LANGCHAIN_TRACING_V2=true`** 는 prompt/response 내용을 호스트 밖으로 (LangSmith 로) 보내는 유일한 경로이다. 라이브러리는 이를 자동으로 활성화하지 않는다. 프로덕션 환경은 unset 으로 둬야 한다.
5. **`MemcachedBackend` 실패는 fail-closed** — 로컬 한정 라운드 로빈으로 조용히 degrade 하지 않고 `BackendUnavailable` 을 raise 한다. 조용한 degrade 는 트래픽이 한 provider 에 집중되는 것을 인지하지 못하게 만든다.

위를 우회해 자격증명을 누출하는 방법을 찾았다면 — 그것이 우리가 원하는 종류의 보고이다.

---

## 조율된 공개

표준 90일 조율된 공개를 따른다. 발견을 공개할 의도라면 (talk, blog post, CVE) 우리가 먼저 수정을 출시할 수 있도록 시점을 조율해 달라. 수정이 더 빨리 land 되면 즉시 릴리즈하고 changelog 에서 크레딧 한다.
