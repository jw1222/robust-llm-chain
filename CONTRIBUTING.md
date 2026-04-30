# Contributing to robust-llm-chain

> Personal-scale OSS — single maintainer, no dependency on outside contributions. PRs and issues are still welcome.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before opening a non-trivial PR. The module structure / call lifecycle / extension points there are the contract; PRs that contradict it will be redirected.

---

## TL;DR (5-minute pre-PR check)

1. `make lint && make type && make test` passes locally.
2. New code follows the **TDD cycle** — RED → GREEN → REFACTOR → COMMIT (one commit per cycle).
3. Commit messages use [Conventional Commits](https://www.conventionalcommits.org/) (`feat(scope): …`, `fix(scope): …`, `refactor(scope): …`).
4. No API keys, AWS access keys, or other secrets in any committed file (including PR description). The `__repr__` on `ProviderSpec` masks live values, but commits don't.
5. Public-API changes (anything in `robust_llm_chain.__init__.__all__` or the documented subpaths) need a prior issue for alignment.

---

## Environment setup — uv only

This project uses [uv](https://docs.astral.sh/uv/) exclusively. Do not introduce poetry / pip-tools / pdm.

```bash
# Install uv if missing
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone + install (creates .venv automatically, full extras)
git clone https://github.com/jw1222/robust-llm-chain.git
cd robust-llm-chain
uv sync --all-extras

# Verify
make lint    # ruff check + ruff format --check
make type    # mypy --strict src/robust_llm_chain
make test    # pytest unit only (integration/e2e auto-skip without keys)
```

`uv.lock` is committed — every contributor uses identical pinned versions. If you need to upgrade a dependency, run `uv lock --upgrade` and explain in the PR description.

> **Switching Python version locally**: if you run `uv run --python 3.11 ...` (or `3.12`) once, uv recreates `.venv` against that interpreter and **dev tools (ruff, mypy, pytest) may drop**. Re-run `uv sync --all-extras --python 3.11` (or `make setup`) before `make check`. CI is unaffected because `uv sync --all-extras --python ${{ matrix.python-version }}` runs first in every matrix job.

---

## Contribution types

### 1) Bug reports / feature requests (issues)

Use the GitHub issue templates (`.github/ISSUE_TEMPLATE/`). Bug reports should include:

- A minimum reproduction
- Expected vs actual behavior
- Python version, OS, the adapter(s) involved (`anthropic` / `openrouter` / `openai` / `bedrock`)
- A traceback — **manually scrub credential patterns first**; the repo's masking only covers runtime objects, not anything you paste into a comment box
- Whether `LANGCHAIN_TRACING_V2` was enabled

**Hard rule:** never paste an API key, AWS access key, or LangSmith token into an issue, PR description, or commit message. There is no automatic masking for those channels.

### 2) Code PRs

#### Requires a prior issue

- Public API changes (anything exported from `robust_llm_chain.__init__`)
- New fields on `ProviderSpec` / `ModelSpec` / `ChainResult` / etc.
- Changes to the exception hierarchy or `is_fallback_eligible` classification
- New core or extras dependencies
- Anything that crosses the v0.1 / v0.2 scope line documented in CHANGELOG

#### No issue needed

- Bug fixes (with a regression test)
- Documentation typos / clarifications
- Internal refactors that don't change the public API
- Additional `FakeAdapter` test scenarios
- CI improvements

#### TDD cycle (enforced)

For every new or modified feature:

1. **RED** — write a failing test first.
2. **GREEN** — write the minimum implementation that makes it pass. No extras.
3. **REFACTOR** — same behavior, cleaner shape. Re-run tests.
4. **COMMIT** — one Conventional Commits message per cycle.

Test-after-code (writing the implementation first and adding tests later) is rejected. The single exception is a pure refactor with no behavior change — say so explicitly in the commit body.

#### Breaking-change checklist

A change is **breaking** (CHANGELOG must say so; bump 0.x minor or follow deprecation cycle in 1.x+) if it:

- Removes / renames anything in `robust_llm_chain.__init__.__all__`
- Removes a field from a public dataclass, changes its type, or changes its semantic meaning
- Removes a public exception class or changes its parent
- Renames a recognized env var or changes its activation rules
- Changes how `is_fallback_eligible` classifies an existing exception family
- Changes a default timeout, default backend, or default adapter behavior
- Changes the lifecycle of `chain.last_result`

Not breaking:

- Anything with a leading underscore
- Changes inside a module not surfaced through `__init__` or a documented subpath
- Tests, CI, build configuration

### 3) Documentation PRs

- Match the surrounding language. README is English; commit messages in Korean or English are both acceptable, just stay consistent within one commit.
- Code docstrings are English (Google style).
- When you cross-reference a section, double-check the anchor still exists after your edit.

---

## PR description checklist

Paste this at the top of every PR:

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

For vulnerabilities (credential leaks, RCE, dependency CVEs, etc.) **do not open a public issue**. See [SECURITY.md](SECURITY.md) for the private reporting path.

If you accidentally commit a credential, rotate the key immediately at the provider, then force-push to drop the blob. History rewrites alone do not invalidate the leaked key — rotation comes first.

---

## Recurring questions

**Q: In `chain.acall("hi", max_tokens=20)`, is `max_tokens` a model option or a template variable?**
A model option. `acall(prompt, *, max_tokens=None, temperature=None, config=None, **template_inputs)` makes the call options keyword-only and explicit; `**template_inputs` only collects names that aren't in the explicit list. So `max_tokens` always routes to the model, never to a `ChatPromptTemplate` variable.

**Q: What happens when `from_env` sees a typo like `model_ids={"antrophic": "..."}`?**
The unknown type is silently skipped. If no providers end up active, `NoProvidersConfigured` is raised. Future versions may tighten the `model_ids` key type.

**Q: gunicorn × N workers + Memcached down — what does the chain do?**
**fail-closed.** `MemcachedBackend.get_and_increment` raises `BackendUnavailable`. The library does **not** silently fall back to `LocalBackend` because that would silently break the worker-coordinated round-robin guarantee — multiple workers would start hammering the same provider. Catch the error in your application and decide explicitly (rebuild chain with `LocalBackend()`, fail the request, trip a circuit breaker, etc.). For genuine fail-open behavior, write a thin `FailoverBackend` wrapper — example in [ARCHITECTURE.md §7.3](ARCHITECTURE.md#73-fail-closed-semantics-for-shared-backends).

**Q: Where do I see partial output if streaming fails mid-flight?**
After `StreamInterrupted`, `chain.last_result` carries the partial `output.content` and the full `attempts` list. The `last_result` is `contextvars`-scoped, so concurrent `astream` calls don't bleed into each other.

**Q: How do I add a new provider?**
Implement the `ProviderAdapter` Protocol (4 lines: `type` ClassVar + `build(spec)` + `credentials_present(env)`) and call `register_adapter(MyAdapter())`. Built-in adapters use exactly the same Protocol — see [ARCHITECTURE.md §7.1](ARCHITECTURE.md#71-new-provider-adapter).

---

## License

MIT. By contributing, you agree your work is licensed under the same terms.
