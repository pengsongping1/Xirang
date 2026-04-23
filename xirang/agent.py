"""Agent — the core loop with streaming, auto-memory, skilllets, and cost tracking.

Flow per turn:
  1. Query recipe cache for fingerprint of user input
  2. Query local skilllets for a reusable workflow shape
  3. Stream LLM response (text printed live by callback)
  4. Execute tool calls in order, append results
  5. Loop until no more tool_use
  6. On success: record trace as recipe + skilllet, scan for auto-memory triggers
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from xirang.config import Config, PROFILE_DEFAULTS, load_config, provider_presets
from xirang.llm import LLM, ChatResult
from xirang.persona import Persona
from xirang import memory as mem
from xirang import recipe as rcp
from xirang import skilllet as skl
from xirang import tools as tl
from xirang import pricing
from xirang import audit
from xirang import permissions
from xirang import session as sess
from xirang import browser as _browser_register  # noqa: F401 — registers 'browser' tool
from xirang import desktop as _desktop_register  # noqa: F401 — registers 'desktop' tool
from xirang import ui


BASE_SYSTEM = """You are Xirang (息壤), a lightweight self-evolving agent.

# Operating principles
- Your toolbox: read_file, write_file, edit_file, bash, grep, glob, write_and_run, search_catalog, http_request, json_query, sqlite_query, csv_query, dispatch_subagent, dispatch_subagent_batch, browser (if playwright is installed), and desktop (if explicitly enabled).
- You DO NOT rely on pre-written skills. Compose primitives dynamically.
- For any "I need capability X" moment, use `bash` or `write_and_run` to create X on the fly.
- Skilllets are your own local, self-grown workflows. Treat them as compact experience, not as stale orders.
- Personas/families are the local companion layer. Skilllets are the local genome layer. Community genome proposals are opt-in artifacts only — never auto-upload anything.
- When a workflow becomes stable, the user can inspect it with `/genome status` and export a sanitized gene proposal with `/genome propose`.
- For web/API tasks: prefer `http_request` for clean API calls and webhooks, `bash curl` for quick static fetches, `browser` for JS-rendered or multi-step flows, and `json_query` for inspecting API responses.
- For local data tasks: prefer `sqlite_query` for SQLite databases and `csv_query` for CSV/TSV exports before writing ad-hoc scripts.
- For human desktop co-pilot tasks: use `desktop` only when the user explicitly wants mouse/keyboard/screenshot collaboration. It is opt-in and disabled unless XIRANG_DESKTOP_ENABLE=1. Work in small reversible steps, because the human may keep controlling the mouse and keyboard alongside you.
- For API/model discovery: call `search_catalog` first. If a matching API or free/local LLM provider is found, reuse that before searching the web again.
- For parallel/isolated work: `dispatch_subagent` spawns a clean context with the same tools.
- Be terse. Respond in 2-3 sentences unless explicitly asked for more.
- When you successfully complete a task, Xirang auto-saves the tool sequence as a recipe and skilllet — next similar task will be faster.
- When the user teaches you something durable ("remember X", "I am Y", "never do Z"), Xirang auto-saves it as a memory.
- Persistent User Rules in memory are active defaults across sessions. Follow them unless the user explicitly changes or removes them.

# Task flow
- Plan silently, act directly. No long preambles.
- One brief sentence before a tool call is fine; zero is also fine.
- When done, give a short summary (≤2 sentences) — never repeat what's in the tool output.
"""


# ---- auto-memory triggers ----
_TRIGGERS_USER = [
    (r"(?:我是|我叫|my name is|i am|i'm)\s*([^。\n！？.!?]{2,60})", "user"),
    (r"(?:我的|my)\s*(?:角色|职位|role|job)\s*(?:是|is)?\s*([^。\n！？.!?]{2,80})", "user"),
]
_TRIGGERS_RULE = [
    (r"(?:不要|别|don'?t|never)\s+([^。\n！？.!?]{3,120})", "rule"),
    (r"(?:以后|从现在起|永远|always|from now on)\s*([^。\n！？.!?]{3,140})", "rule"),
    (r"(?:记住|remember)\s*[，,:]?\s*([^。\n！？.!?]{3,140})", "rule"),
]
_TRIGGERS_PROJECT = [
    (r"(?:我们在做|we are working on|this project is)([^。\n！？.!?]{3,120})", "project"),
]


def _scan_for_memory(text: str) -> list[tuple[str, str, str]]:
    """Return [(name, description, type)] for any durable info in text."""
    out: list[tuple[str, str, str]] = []
    for pattern, mem_type in _TRIGGERS_USER + _TRIGGERS_RULE + _TRIGGERS_PROJECT:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            captured = m.group(m.lastindex or 1).strip().strip(".,。！!")
            if len(captured) < 3:
                continue
            name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", captured)[:40]
            out.append((name or f"mem_{len(out)}", captured[:100], mem_type))
    return out


@dataclass
class AgentTurn:
    user_input: str
    tool_trace: list[dict] = field(default_factory=list)
    success: bool = False
    text_output: str = ""


class Agent:
    def __init__(self, cfg: Config, persona: Optional[Persona] = None, use_recipes: bool = True):
        self.cfg = cfg
        self.llm = LLM(cfg)
        self.persona = persona
        self.persona_mode: str | None = None
        self.use_recipes = use_recipes
        self.messages: list[dict] = []
        self.tools = tl.all_tools()
        self.current_session_name = "last"
        self.last_saved_at = 0.0
        # cumulative usage across turns
        self.total_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
        self.started_at = time.time()
        self.turn_count = 0

    def _system_prompt(self, query: str = "", workflow_hint: str = "") -> str:
        parts = [BASE_SYSTEM]
        if self.persona:
            parts.append("\n" + self.persona.to_system_augmentation(self.persona_mode))
        parts.append(
            mem.render_for_system_prompt(
                self.cfg.memory_dir,
                query=query,
                budget_bytes=self.cfg.memory_context_budget_bytes,
            )
        )
        if self.persona:
            parts.append(skl.render_family_index(self.cfg.skilllets_dir, self.cfg.personas_dir, self.persona.slug))
        else:
            parts.append(skl.render_index(self.cfg.skilllets_dir))
        if workflow_hint:
            parts.append(workflow_hint)
        return "\n".join(p for p in parts if p)

    def _accumulate_usage(self, usage: dict) -> None:
        for k, v in usage.items():
            if isinstance(v, (int, float)):
                self.total_usage[k] = self.total_usage.get(k, 0) + v

    def turn(self, user_input: str, max_iters: int | None = None) -> AgentTurn:
        turn = AgentTurn(user_input=user_input)
        max_iters = max_iters or self.cfg.max_tool_iters

        # 1. Recipe lookup (fast path)
        workflow_hint = ""
        if self.use_recipes:
            hit = rcp.lookup(self.cfg.recipes_path, user_input)
            if hit:
                ui.status(f"recipe hit: {hit.intent_sample[:60]}... (used {hit.hit_count}x)")
                workflow_hint += rcp.render_hint(hit)
            skilllet_hit = skl.lookup(
                self.cfg.skilllets_dir,
                user_input,
                owner_slug=self.persona.slug if self.persona else "",
                personas_dir=self.cfg.personas_dir,
            )
            if skilllet_hit:
                owner_note = f" from {skilllet_hit.owner_slug}" if skilllet_hit.owner_slug and skilllet_hit.owner_slug != (self.persona.slug if self.persona else "") else ""
                ui.status(f"skilllet hit: {skilllet_hit.slug}{owner_note} (used {skilllet_hit.hit_count}x)")
                workflow_hint += skl.render_hint(skilllet_hit)

        # 2. Auto-memory scan on user input
        captured = _scan_for_memory(user_input)
        for name, desc, mtype in captured:
            if mtype == "rule":
                mem.save_rule(self.cfg.memory_dir, name=name, body=desc, description=desc, source="auto_rule")
            else:
                mem.save_memory(self.cfg.memory_dir, name=name, description=desc, mem_type=mtype, body=desc)
            ui.status(f"auto-memory saved: [{mtype}] {desc[:60]}")

        # 3. Append user message
        self.messages.append({"role": "user", "content": user_input})
        system = self._system_prompt(query=user_input, workflow_hint=workflow_hint)

        # 4. Agent loop (streaming)
        final_text = ""
        for i in range(max_iters):
            text_started = [False]

            def on_text(chunk: str) -> None:
                if not text_started[0]:
                    sys.stdout.write(ui.ASSIST_MARK)
                    text_started[0] = True
                sys.stdout.write(chunk)
                sys.stdout.flush()

            try:
                result: ChatResult = self.llm.chat(
                    messages=self.messages, system=system, tools=self.tools,
                    max_tokens=self.cfg.max_output_tokens,
                    on_text=on_text,
                )
            except Exception as e:
                if text_started[0]:
                    sys.stdout.write("\n")
                ui.error(f"LLM call failed: {type(e).__name__}: {e}")
                return turn

            # finish streaming line
            if text_started[0]:
                sys.stdout.write("\n")

            self._accumulate_usage(result.usage)
            if i == 0 and result.usage.get("cache_read", 0) > 0:
                ui.status(f"cache read: {result.usage['cache_read']} tokens")

            self.messages.append({"role": "assistant", "content": result.raw_assistant_content})
            if result.text:
                final_text = result.text

            if not result.tool_calls:
                turn.success = True
                break

            # execute tool calls
            tool_results: list[dict] = []
            for tc in result.tool_calls:
                ui.tool_call_panel(tc.name, tc.args)
                t = tl.get_tool(tc.name)
                decision = permissions.decide(self.cfg.mode, tc.name, tc.args)
                audit.record(
                    self.cfg.audit_path,
                    "tool_decision",
                    {
                        "mode": self.cfg.mode,
                        "tool": tc.name,
                        "category": decision.category,
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "risk": getattr(decision, "risk", "low"),
                        "args_keys": sorted(tc.args.keys()),
                    },
                )
                if not t:
                    output = f"Error: unknown tool '{tc.name}'"
                elif not decision.allowed:
                    output = f"Permission denied: {decision.reason}"
                else:
                    output = t.run(tc.args)
                audit.record(
                    self.cfg.audit_path,
                    "tool_result",
                    {
                        "tool": tc.name,
                    "allowed": decision.allowed,
                    "risk": getattr(decision, "risk", "low"),
                    "output_chars": len(output),
                    "ok": not output.startswith("Error:") and not output.startswith("Permission denied:"),
                },
                )
                ui.tool_result_panel(tc.name, output)
                turn.tool_trace.append({
                    "tool": tc.name,
                    "args_keys": sorted(tc.args.keys()),
                    "allowed": decision.allowed,
                    "category": decision.category,
                    "risk": getattr(decision, "risk", "low"),
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output,
                })

            self.messages.append({"role": "user", "content": tool_results})
        else:
            ui.warn(f"max iterations ({max_iters}) reached")

        # 5. Record recipe on success
        if turn.success and turn.tool_trace and self.use_recipes:
            rcp.record(self.cfg.recipes_path, user_input, turn.tool_trace)
            saved = skl.upsert_from_trace(
                self.cfg.skilllets_dir,
                user_input,
                turn.tool_trace,
                owner_slug=self.persona.slug if self.persona else "",
            )
            if saved:
                ui.status(f"skilllet updated: {saved.slug}")

        turn.text_output = final_text
        self.turn_count += 1
        # 6. Cost line at end of turn
        u = self.total_usage
        if u["input"] + u["output"] > 0:
            parts = [f"in={u['input']}", f"out={u['output']}"]
            if u.get("cache_read"):
                parts.append(f"cache_read={u['cache_read']}")
            cost = pricing.compute_cost(u, self.cfg.model)
            parts.append(pricing.format_cost(cost))
            ui.status("tokens · " + "  ".join(parts))
        try:
            mem.capture_turn(
                self.cfg.memory_dir,
                self.current_session_name,
                user_input,
                turn.text_output,
                self.turn_count,
                persona_slug=self.persona.slug if self.persona else "",
            )
        except Exception:
            pass
        self._autosave_runtime_state()

        return turn

    def run_silent(self, task: str, max_iters: int | None = None) -> str:
        """For subagents: execute a task silently, return final text output.

        No UI panels, no recipe recording, no streaming to stdout.
        """
        self.use_recipes = False
        self.messages = []
        self.messages.append({"role": "user", "content": task})
        system = self._system_prompt(query=task)
        final_text = ""

        for _ in range(max_iters or self.cfg.max_tool_iters):
            try:
                result = self.llm.chat(
                    messages=self.messages,
                    system=system,
                    tools=self.tools,
                    max_tokens=self.cfg.max_output_tokens,
                )
            except Exception as e:
                return f"Error: {e}"

            self.messages.append({"role": "assistant", "content": result.raw_assistant_content})
            if result.text:
                final_text = result.text

            if not result.tool_calls:
                return final_text

            tool_results = []
            for tc in result.tool_calls:
                t = tl.get_tool(tc.name)
                decision = permissions.decide(self.cfg.mode, tc.name, tc.args)
                audit.record(
                    self.cfg.audit_path,
                    "subagent_tool_decision",
                    {
                        "mode": self.cfg.mode,
                        "tool": tc.name,
                        "category": decision.category,
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "risk": getattr(decision, "risk", "low"),
                        "args_keys": sorted(tc.args.keys()),
                    },
                )
                if not t:
                    output = f"Error: unknown tool '{tc.name}'"
                elif not decision.allowed:
                    output = f"Permission denied: {decision.reason}"
                else:
                    output = t.run(tc.args)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output,
                })
            self.messages.append({"role": "user", "content": tool_results})
        return final_text or "(max iterations reached)"

    def clear(self) -> None:
        self.messages = []
        self.total_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
        self.turn_count = 0
        self.started_at = time.time()

    def reload_runtime_client(self) -> None:
        self.llm = LLM(self.cfg)

    def set_response_profile(self, profile: str) -> str:
        profile = (profile or "").strip().lower()
        if profile not in PROFILE_DEFAULTS:
            raise ValueError(f"unknown profile: {profile}")
        defaults = PROFILE_DEFAULTS[profile]
        self.cfg.response_profile = profile
        self.cfg.max_output_tokens = defaults["max_output_tokens"]
        self.cfg.max_tool_iters = defaults["max_tool_iters"]
        return profile

    def switch_model(self, model: str) -> None:
        model = model.strip()
        if not model:
            raise ValueError("model cannot be empty")
        self.cfg.model = model
        self.reload_runtime_client()

    def switch_provider(self, provider: str) -> None:
        provider = (provider or "").strip().lower()
        if provider not in provider_presets():
            raise ValueError(f"unknown provider: {provider}")
        fresh = load_config(provider_override=provider)
        fresh.home = self.cfg.home
        fresh.audit_path = self.cfg.audit_path
        fresh.recipes_path = self.cfg.recipes_path
        fresh.memory_dir = self.cfg.memory_dir
        fresh.personas_dir = self.cfg.personas_dir
        fresh.skilllets_dir = self.cfg.skilllets_dir
        fresh.catalogs_dir = self.cfg.catalogs_dir
        fresh.mode = self.cfg.mode
        fresh.response_profile = self.cfg.response_profile
        fresh.max_output_tokens = self.cfg.max_output_tokens
        fresh.max_tool_iters = self.cfg.max_tool_iters
        fresh.autosave_on_turn = self.cfg.autosave_on_turn
        self.cfg = fresh
        self.reload_runtime_client()

    def runtime_status(self) -> dict[str, str | int | None]:
        return {
            "provider": self.cfg.provider,
            "model": self.cfg.model,
            "mode": self.cfg.mode,
            "profile": self.cfg.response_profile,
            "max_output_tokens": self.cfg.max_output_tokens,
            "max_tool_iters": self.cfg.max_tool_iters,
            "session": self.current_session_name,
            "persona": self.persona.name if self.persona else None,
            "persona_mode": self.persona_mode or "default",
            "turn_count": self.turn_count,
        }

    def _autosave_runtime_state(self) -> None:
        if not self.cfg.autosave_on_turn or self.turn_count <= 0:
            return
        try:
            sess.save(self.cfg.home, self.current_session_name, self)
            self.last_saved_at = time.time()
        except Exception as e:
            ui.warn(f"autosave failed: {e}")
