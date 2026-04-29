---
name: Feature request
about: Suggest a new feature or enhancement for robust-llm-chain
title: "[feature] "
labels: enhancement
assignees: ''
---

> Read [ARCHITECTURE.md](../../ARCHITECTURE.md) and [CONTRIBUTING.md](../../CONTRIBUTING.md) "Requires a prior issue" before opening. Public-API changes need this issue first so that we align before code is written.

## Motivation — what pain are you hitting?

<!-- Concrete situation, not abstract wishlist. "When provider X returns 5xx I have
     to do Y manually" beats "would be nice to have retries on X". -->

## Proposal

<!-- Sketch the API or behavior. Mention which module(s) it would touch
     (chain.py / adapters/ / backends/ / stream.py / resolver.py / observability/). -->

## Alternatives considered

<!-- What did you try? Why doesn't an existing primitive (custom ProviderAdapter,
     custom IndexBackend, application-level wrapper) cover the case? -->

## Scope impact

- [ ] Stays within v0.1 (Anthropic / OpenRouter / OpenAI / Bedrock + LocalBackend / MemcachedBackend + LangSmith observability)
- [ ] Crosses into v0.2 territory (new backend family, new transport, structured-output policy, etc.)
- [ ] Unsure — needs maintainer review

## Breaking change?

- [ ] No
- [ ] Yes — describe what breaks and the migration path
- [ ] Unsure

## Additional context

<!-- Links to upstream issues, related PRs, traces, benchmarks. Do NOT paste secrets. -->
