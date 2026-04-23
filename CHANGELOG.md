# Changelog

All notable changes to Xirang will be documented in this file.

The project currently follows a lightweight, human-written changelog style.

## 0.2.0a1 - 2026-04-23

This is the first public alpha / preview release candidate.

### Added

- Persona family workflows:
  - distill
  - refine
  - fork
  - birth
  - mutate
  - mate
- Inherited local skill genes (`skilllets`) and family lookup
- Sanitized genome proposal export / review / merge flow
- Layered local memory with:
  - prelude memory
  - recurrent daily journal
  - coda outcomes
  - archive recall
- Optional browser tool for Playwright-based web tasks
- Optional desktop co-pilot tool for explicit local mouse / keyboard / screenshot control
- Explicit `/copilot` session flow
- Provider setup / doctor / live doctor checks
- Local data + interface tools:
  - `http_request`
  - `json_query`
  - `sqlite_query`
  - `csv_query`
- Batch subagent orchestration via `dispatch_subagent_batch`
- Local automation layer:
  - cron-like jobs
  - due-job runner
  - foreground scheduler
  - webhook routes
  - foreground webhook server
- Local benchmark harness with dry-run and CLI entrypoint
- `safe` permission mode with low / medium / high risk classification

### Changed

- Improved CLI ergonomics for automation, benchmark, and risk-aware execution
- Improved release readiness documentation
- Improved README positioning for public-alpha release
- Improved scriptability:
  - `xirang -p ...` now exits non-zero on failure
  - `xirang --doctor-live` now exits non-zero on failure
  - `xirang --bench` exits non-zero if benchmark tasks fail

### Fixed

- Explicit `XIRANG_HOME` no longer implicitly imports the default legacy `~/.morrow` home

### Validation

- Smoke test suite: `43/43` passing at release prep time

### Release Positioning

- Recommended release channel: **public alpha / public preview**
- Recommended framing: **local-first experimental agent**, not mass-market desktop assistant
