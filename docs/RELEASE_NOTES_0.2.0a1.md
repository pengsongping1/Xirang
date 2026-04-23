# Xirang 0.2.0a1 Release Notes

**Release type:** public alpha / public preview  
**Date:** 2026-04-23

Xirang 0.2.0a1 is the first release candidate that presents Xirang as a
local-first, self-evolving personal agent rather than a one-off chat wrapper.

It combines:

- continuous local memory
- persona families
- inherited skill genes
- sanitized genome proposals
- explicit desktop co-pilot sessions
- local API / JSON / SQLite / CSV tooling
- cron-like automation
- webhook ingestion
- benchmark checks
- risk-aware execution modes

## What Is New

### Local Memory That Carries Continuity

Xirang now persists and recalls context across sessions through layered memory:

- **Prelude** for stable facts
- **Recurrent** for daily journal and rolling session summaries
- **Coda** for recent outcomes
- **Archive** for longer-horizon recall

This supports prompts like “继续上次” or “昨天我们聊到哪了” without relying only
on the current context window.

### Persona Families and Skill Genes

Personas can now be distilled, refined, forked, born, mutated, and mated.

Skilllets can be owned by personas. Child personas can inherit matching skill
genes from parents, co-parents, ancestors, and shared local genes.

### Safe Genome Proposal Flow

Xirang does not upload your full child agent, private memory, or full session.

Instead, users can export sanitized genome proposals containing task
fingerprints, tool chains, argument-key structure, success/failure counts,
maturity, and risk signals.

### Real-World Tooling

The default tool surface now includes:

- `http_request` for APIs, webhooks, and health checks
- `json_query` for API response inspection
- `sqlite_query` for local SQLite databases
- `csv_query` for CSV / TSV exports
- `dispatch_subagent_batch` for bounded subagent orchestration

### Automation and Webhooks

Xirang can now run as a small local automation node:

```bash
xirang --scheduler
xirang --serve-webhooks --webhook-host 127.0.0.1 --webhook-port 8765
xirang --run-due-jobs
```

Inside the REPL:

```text
/cron add heartbeat :: @every 5m :: 输出一行当前状态
/webhook add alerts :: 收到告警后总结事件并给出下一步
```

### Benchmark Harness

The release includes a local benchmark harness:

```bash
xirang --bench-dry-run
xirang --bench
python3 benchmarks/run_bench.py --dry-run
```

The benchmark suite currently covers:

- JSON field extraction
- CSV filtering and file writing
- SQLite query summarization
- local HTTP API summarization
- memory follow-up recall

### Risk-Aware Execution

Execution modes now include:

- `default` / `auto`
- `safe`
- `plan`
- `ask`

`safe` mode allows only low-risk tools. `ask` mode auto-allows low-risk tools
and requires confirmation for medium/high-risk tools when a TTY is available.

## Desktop Co-Pilot Status

The desktop co-pilot is implemented but intentionally opt-in.

It supports:

- screenshot
- move
- click
- double click
- drag
- scroll
- type text
- hotkey
- press
- bounded watch

It requires:

```bash
pip install ".[desktop]"
XIRANG_DESKTOP_ENABLE=1 xirang
```

Then:

```text
/copilot start 一起操作桌面
```

The desktop tool does not install a background keylogger and does not silently
monitor user input.

## Known Limits

This is not yet a stable mass-market desktop assistant.

Known alpha limitations:

- no full OpenClaw-style multi-channel gateway yet
- no packaged background daemon installer yet
- browser / desktop workflows need more real-world templates
- benchmark suite is useful but still small
- desktop operation depends on OS GUI permissions and optional dependencies

## Recommended GitHub Release Title

`Xirang 0.2.0a1 — local-first self-evolving agent public alpha`

## Recommended GitHub Release Summary

Xirang is a local-first personal agent that remembers, grows persona families,
inherits self-grown skill genes, exports sanitized genome proposals, and can
optionally co-pilot your desktop with explicit permission.

This alpha adds real-world engineering breadth: API/JSON/SQLite/CSV tools,
cron-like automation, webhook ingestion, batch subagents, benchmark checks, and
risk-aware execution modes.

## Validation

Release prep validation:

```bash
python3 tests/test_smoke.py
```

Expected result:

```text
All 43 tests passed.
```
