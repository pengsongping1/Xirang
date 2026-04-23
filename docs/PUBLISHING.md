# Publishing Xirang 0.2.0a1

This checklist is for a public alpha / public preview release, not a stable GA
launch.

## Positioning

- Release title: `Xirang 0.2.0a1 — local-first self-evolving agent public alpha`
- Release channel: public alpha / public preview
- Main promise: local-first agent with memory, persona families, inherited skill
  genes, sanitized genome proposals, optional desktop co-pilot, automation,
  webhooks, and benchmark checks
- Do not claim: stable mass-market desktop assistant, hidden monitoring tool, or
  full OpenClaw-style gateway/channel/daemon platform

## Required Local Validation

Run from the repository root:

```bash
python3 -m py_compile xirang/*.py scripts/*.py benchmarks/run_bench.py
python3 tests/test_smoke.py
PYTHONPATH=. XIRANG_HOME="$(mktemp -d)" XIRANG_PROVIDER=ollama python3 -m xirang --bench-dry-run
```

Expected smoke result:

```text
All 43 tests passed.
```

## Optional Desktop Validation

Desktop control is intentionally opt-in and depends on GUI permissions:

```bash
pip install ".[desktop]"
XIRANG_DESKTOP_ENABLE=1 xirang
```

Then in the REPL:

```text
/copilot status
/copilot start 发布前桌面验证
/copilot screenshot
/copilot stop
```

If `pyautogui_available` is false, publish can still proceed as alpha, but the
release notes should state that desktop control requires the optional
dependencies and OS GUI permission.

## Build Artifacts

```bash
python3 -m pip install --upgrade build twine
python3 -m build
python3 -m twine check dist/*
```

Publish only after reviewing the generated package contents.

## GitHub Release Body

Use `docs/RELEASE_NOTES_0.2.0a1.md` as the release body and keep the “Known
Limits” section. Link `CHANGELOG.md`, `SECURITY.md`, and `CONTRIBUTING.md`.

## Final Manual Checks

- README says `0.2.0a1 Public Alpha / Public Preview`
- `pyproject.toml` and `xirang/__init__.py` both say `0.2.0a1`
- `.env`, `.venv`, `.xirang`, and generated exports are not included
- Desktop co-pilot is described as explicit opt-in
- Genome proposal flow says it exports sanitized skill genes, not private memory
- Demo GIF is recommended but not blocking for a developer alpha
