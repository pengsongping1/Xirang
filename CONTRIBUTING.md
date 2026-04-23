# Contributing to Xirang

Thanks for helping Xirang evolve.

## Good Contributions

- Bug fixes with a small reproduction.
- Docs and examples that make local-first use clearer.
- New smoke tests for memory, persona families, skill inheritance, genome review,
  browser, or desktop co-pilot behavior.
- Sanitized genome proposals created with `/genome propose`.

## Genome Proposal Flow

```text
/genome status
/genome propose
/genome review ~/.xirang/exports/<proposal>.json
```

Then open a PR with the proposal file or with the reviewed/merged output.

Please do not submit:

- API keys, tokens, cookies, or local paths.
- Full chat logs, private memories, or full persona families unless intentionally
  shared as examples.
- Genes that depend on hidden monitoring or automatic network upload.

## Local Validation

```bash
python3 -m py_compile xirang/*.py scripts/*.py
python3 tests/test_smoke.py
python3 -m xirang --help
```

Desktop and browser integrations are optional extras. Keep tests safe when those
extras are not installed.
