## Summary

<!-- One or two sentences: what changes and why. -->

## Related issue

<!-- Required if the PR changes anything in `robust_llm_chain.__init__.__all__` or
     a documented subpath, adds/removes a public dataclass field, or crosses
     the v0.1 / v0.2 scope line. See CONTRIBUTING.md "Requires a prior issue". -->

Closes #...

## Type of change

- [ ] Bug fix (non-breaking, with regression test)
- [ ] New feature (non-breaking)
- [ ] Breaking change (see checklist below)
- [ ] Documentation only
- [ ] Internal refactor (no behavior change)
- [ ] CI / build configuration

## Breaking change?

<!-- See CONTRIBUTING.md "Breaking-change checklist" for the full list.
     If yes, name what breaks and how downstream users migrate. Update CHANGELOG accordingly. -->

- [ ] No
- [ ] Yes — described below

## How was this tested?

<!-- Concrete steps. "make test" alone is not enough for non-trivial changes. -->

## Pre-merge checklist

- [ ] Aligns with ARCHITECTURE.md (module layout, call lifecycle, extension contracts)
- [ ] Prior-issue link if changing public API or scope: #...
- [ ] TDD cycle followed (RED -> GREEN -> REFACTOR per cycle, one commit each)
- [ ] New tests added or existing tests updated
- [ ] `make lint` passes (ruff + ruff format --check)
- [ ] `make type` passes (mypy --strict)
- [ ] `make test` passes (unit)
- [ ] CHANGELOG.md updated if user-visible
- [ ] Breaking change called out per checklist above
- [ ] No credentials or local-path leaks in diff or description
