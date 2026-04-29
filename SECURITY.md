# Security Policy

## Supported versions

This project is in pre-1.0 active development. Only the latest `0.x` release receives security fixes.

| Version | Supported |
|---|---|
| Latest `0.x` | ✓ |
| Older `0.x` | ✗ — upgrade to latest |

Once `1.0` ships, the support window will be defined here.

---

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.**

Use **GitHub Security Advisories** (private) instead:

1. Go to <https://github.com/jw1222/robust-llm-chain/security/advisories/new>
2. Describe the vulnerability with a minimum reproduction
3. Wait for an acknowledgement (target: within 7 days)

If you cannot use Security Advisories, email the maintainer (address listed on the GitHub profile). Encrypt with the maintainer's public key when possible.

### What to include

- Affected version(s) and platform
- Reproduction steps or proof-of-concept
- Impact assessment (confidentiality / integrity / availability)
- Suggested fix, if you have one

### What you can expect

| Stage | Target |
|---|---|
| Acknowledgement | within 7 days |
| Triage + initial assessment | within 14 days |
| Fix or mitigation plan | within 30 days for High / Critical |
| Coordinated disclosure | typically 90 days from report; sooner if a fix ships earlier |

Credit will be given in the CHANGELOG and release notes unless you prefer to remain anonymous.

---

## Scope

### In scope

- Code execution / privilege escalation through library APIs
- Credential exposure in logs, exception messages, `repr()`, or LangSmith traces
- Bypass of `_security.sanitize_message` masking patterns
- Injection vulnerabilities in adapter / backend layers
- Denial-of-service via crafted inputs that bypass timeouts
- Vulnerabilities in pinned dependency versions (`uv.lock`)

### Out of scope

- Vulnerabilities in user code that uses this library incorrectly (e.g. logging `result.input` to an unauthenticated channel)
- Vulnerabilities in upstream providers (Anthropic, OpenAI, OpenRouter, AWS) — report those upstream
- Issues requiring physical access to the user's machine
- Self-XSS in unrelated tooling
- Bugs reproducible only with `# type: ignore` / monkey-patching of internal symbols

---

## Hardening guarantees the library tries to give you

These are part of the public contract — if any breaks in a release, that's a security regression worth reporting:

1. **`ProviderSpec` credential masking — covered paths**: `repr(spec)` / `str(spec)` (custom `__repr__` plus `field(repr=False)`), `vars(spec)` / `spec.__dict__` (blocked by `slots=True`), equality / hashing (`compare=False` on credential fields — prevents pytest assertion introspection from printing credentials in failure diffs), and `pickle.dumps(spec)` (custom `__getstate__` strips credentials before serialization). The same `__getstate__` is used by `copy.copy(spec)` and `copy.deepcopy(spec)` — credentials are dropped (set to `None`) on the copy. If you intend to copy a `spec` for runtime reuse (not just serialization), construct a new `ProviderSpec` with the credential explicitly rather than copying. **Not covered** — `dataclasses.asdict(spec)` and `dataclasses.astuple(spec)` traverse all fields unconditionally and expose credentials in plaintext. The same applies recursively to **`dataclasses.asdict(chain_result)`**: because `ChainResult.provider_used` holds a `ProviderSpec`, calling `asdict()` on a result will surface credentials in the nested dict. `pydantic.BaseModel.model_dump()` likewise exposes any `ProviderSpec` it embeds. **For logging `ProviderSpec`, use `repr(spec)` (the custom `__repr__` masks credentials).** Do **not** rely on `repr(chain_result)` — `ChainResult` uses the default dataclass repr, which exposes `input` (prompt) and `output` (response) in plaintext. Hardening #3 makes this the application's responsibility: extract the specific fields you want to persist (`result.provider_used.id`, `result.elapsed_ms`, `result.usage`, `result.attempts`) rather than dumping the whole result. Never use `dataclasses.asdict(...)` on either type.
2. **`AttemptRecord.error_message`** is sanitized via `_security.sanitize_message` — provider API key prefixes, AWS access key id format, and LangSmith personal token format (see `src/robust_llm_chain/_security.py` `_KEY_PATTERNS` for the exact regexes) are replaced with `***`, then the string is truncated to 200 chars. Best-effort only: less common token formats (LangSmith service tokens, AWS STS / temporary credentials) and provider-specific variants are not currently in the pattern set, and the catch-all 40-character base64 pattern can mask non-credential strings (false positives). Open an issue if you encounter a real credential prefix that escapes masking.
3. **The library itself never logs prompt or response text.** Audit logging of `ChainResult.input` / `ChainResult.output` is the application's responsibility — the library only emits structured metadata (provider id, elapsed_ms, error type) at WARN/ERROR level.
4. **`LANGCHAIN_TRACING_V2=true`** is the only path that sends prompt/response content off-host (to LangSmith). The library does not enable it for you. Production environments should leave it unset.
5. **`MemcachedBackend` failures are fail-closed** — they raise `BackendUnavailable` rather than silently degrading to local-only round-robin. Silent degradation would mean traffic concentration on one provider without you noticing.

If you find a way to leak credentials that bypasses the above — that's the kind of report we want.

---

## Coordinated disclosure

We follow standard 90-day coordinated disclosure. If you intend to publish your finding (talk, blog post, CVE), please coordinate the timing so we can ship a fix first. If a fix lands earlier we'll release immediately and credit you in the changelog.
