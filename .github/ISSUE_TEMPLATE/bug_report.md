---
name: Bug report
about: Report unexpected behavior in robust-llm-chain
title: "[bug] "
labels: bug
assignees: ''
---

> **Before posting:** scrub any provider API key, AWS access key, or LangSmith token from the traceback and reproduction. There is no automatic masking on issue text — `ProviderSpec.__repr__` masks runtime objects, not anything you paste into a comment box. If you are unsure what to look for, see `src/robust_llm_chain/_security.py` for the recognized credential patterns.

## Summary

<!-- One sentence: what went wrong. -->

## Reproduction

<!-- Minimum code that triggers the bug. Use FakeAdapter where possible so that
     the repro does not need real credentials. See tests/ for examples. -->

```python
# minimum repro
```

## Expected behavior

## Actual behavior

## Environment

- **robust-llm-chain version:** <!-- e.g. 0.1.0 -->
- **Python version:** <!-- e.g. 3.12.4 -->
- **OS:** <!-- e.g. Ubuntu 22.04, macOS 14, Windows 11 + WSL2 -->
- **Adapter(s) involved:** <!-- anthropic / openrouter / openai / bedrock / custom -->
- **Backend:** <!-- LocalBackend / MemcachedBackend / custom -->
- **`LANGCHAIN_TRACING_V2` enabled?** <!-- yes / no -->
- **uv version (if relevant):** `uv --version`

## Traceback

<!-- Paste the full traceback. SCRUB CREDENTIALS FIRST. -->

```
```

## Additional context

<!-- LangSmith run URL (if shareable), upstream provider status pages, anything
     else that helps. Do NOT paste secrets, even masked. -->
