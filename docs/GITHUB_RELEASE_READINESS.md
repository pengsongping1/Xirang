# Xirang GitHub Release Readiness

This document is a practical release assessment for making Xirang impactful
without over-claiming.

## Current Status

**Recommended release level:** public alpha.

The project is ready to publish as `0.2.0a1`, a local-first experimental
agent / public alpha, if the README positions it honestly: the core loop,
persona family, inherited skilllets, genome proposals, long-horizon memory,
browser tool, desktop tool, local data/API tools, automation, webhook
ingestion, benchmark checks, provider setup, doctor checks, risk-aware
permission modes, and smoke tests all exist.

It is not yet a polished mass-market desktop app. The current interface is CLI
first, with optional browser and desktop control tools.

## High-Impact Differentiators

1. **Persona families**
   - Personas can be distilled, refined, forked, born, mutated, and mated.
   - Family trees are persisted as local Markdown.

2. **Inherited skill genes**
   - Skilllets are owned by personas.
   - Child personas can reuse parent, co-parent, and ancestor workflows.

3. **Local long-horizon memory**
   - Sessions persist.
   - Daily journals and continuity recall help answer “上次 / 昨天 / 继续”.

4. **Genome proposal model**
   - Users do not upload full children or private memory.
   - They can export sanitized skill gene proposals for manual PRs.

5. **Human + agent desktop co-pilot**
   - Optional `desktop` tool can screenshot, move, click, type, press hotkeys,
     scroll, drag, and run short bounded watch sessions.
   - `/copilot start|observe|invite|stop` turns this into an explicit
     human-in-the-loop collaboration session instead of hidden monitoring.
   - Disabled by default and auditable through the permission system.

6. **Low-cost provider path**
   - `openrouter` preset defaults to a free model.
   - `ollama` and `lmstudio` support local use.

7. **Local automation node**
   - Cron-like jobs can persist and run due tasks.
   - Webhook routes can ingest external events into named Xirang sessions.
   - The foreground scheduler/server make it usable as a small local
     automation workbench without claiming a full distributed gateway.

8. **Benchmark and scriptability loop**
   - `--bench-dry-run` validates task definitions without LLM calls.
   - `--bench` writes machine-readable results and exits non-zero on failure.
   - `-p`, `--doctor-live`, and benchmark commands now behave better in CI and
     shell automation.

## Sibling Project Audit

I checked the adjacent projects under `xmsagent/` and folded the strongest
release lessons into Xirang without making it a copy:

- **GenericAgent:** atomic tools, OS control, memory crystallization, and skill
  reuse are covered by `tools.py`, optional browser/desktop tools, daily memory,
  recipes, persona-owned skilllets, and local API/JSON/SQLite/CSV tooling.
- **OhMyCode:** small CLI-first coding-agent ergonomics are covered by streaming
  REPL, permission modes, sessions, smoke tests, package entry points, CI smoke,
  and benchmark dry-runs.
- **OpenClaw:** local-first positioning, onboarding, and security framing are
  covered by `--setup`, `--doctor`, explicit `/copilot`, audit logs, and
  safe/plan/ask/default execution modes. Automation and webhooks cover the first
  local-node layer; a full gateway/channel/daemon platform is still outside this
  public-alpha scope.
- **nuwa-skill:** person distillation and honest limits are covered by persona
  distillation, style modes, `limits`, family trees, and import/export bundles.

## What Is Actually Implemented

- CLI entry: `xirang`
- Setup: `xirang --setup <provider>`
- Health checks: `xirang --doctor`, `xirang --doctor-live`
- Personas: `/persona distill`, `/persona birth`, `/persona mutate`, `/persona mate`
- Memory: `/memory recent`, `/memory search`, `/session save`, `/session load`
- Skilllets: `/skilllets`, `/skilllets family`
- Genome: `/genome status`, `/genome propose`, `/genome review`
- Automation: `/cron add`, `/cron list`, `/cron run`, `--scheduler`,
  `--run-due-jobs`
- Webhooks: `/webhook add`, `/webhook list`, `/webhook serve`,
  `--serve-webhooks`
- Data/API tools: `http_request`, `json_query`, `sqlite_query`, `csv_query`
- Benchmark: `/bench dry-run`, `--bench-dry-run`, `--bench`
- Browser: optional Playwright `browser` tool
- Desktop: optional pyautogui `desktop` tool
- Co-pilot session: `/copilot status`, `/copilot start`, `/copilot observe`,
  `/copilot screenshot`, `/copilot invite`, `/copilot stop`
- Tests: `python3 tests/test_smoke.py` (`43/43` passing at release prep time)

## Safety Positioning

Do not advertise Xirang as a hidden monitoring agent.

The correct framing is:

- local-first
- user-controlled
- explicit desktop co-pilot
- visible `/copilot` session instead of background input capture
- no background keylogger
- no automatic network sync
- high-risk tools blocked in `plan` mode and confirmable in `ask` mode

## Before a Bigger Launch

For maximum GitHub impact, add:

- a 30–60 second demo GIF:
  - resume yesterday’s conversation
  - switch persona
  - show family tree
  - run `/genome propose`
  - enable desktop and perform a visible click/type task
- 3 example workflows in `examples/`
- GitHub Actions smoke test
- screenshots of the CLI panels
- a short “why Xirang is different” image or diagram

## Release Checklist

- [x] README explains the product without copycat framing
- [x] MIT license file exists
- [x] `CONTRIBUTING.md` and `SECURITY.md` describe safe contribution flow
- [x] `.env`, `.venv`, `.xirang`, and generated exports are gitignored
- [x] Smoke tests pass
- [x] Version bumped to `0.2.0a1`
- [x] Release notes added
- [x] Changelog added
- [x] Publish checklist added
- [x] Optional desktop control is disabled by default
- [x] Explicit `/copilot` session wrapper added
- [x] Genome proposal does not upload full private state
- [x] Automation, webhook, and benchmark commands documented
- [ ] Demo GIF recorded
- [x] GitHub Actions workflow added
- [x] Examples populated

## Recommended GitHub Tagline

> Local-first agent that remembers, grows persona families, inherits skill genes,
> and can co-pilot your desktop — without auto-uploading your private evolution.
