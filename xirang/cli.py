"""CLI — entry point, REPL, slash commands."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path

from xirang import bundle as bun
from xirang import automation as auto
from xirang import benchmark as bench
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from xirang import memory as mem
from xirang import catalog as cat
from xirang import copilot as co
from xirang import persona as per
from xirang import pricing
from xirang import recipe as rcp
from xirang import session as sess
from xirang import setup as setup_mod
from xirang import skilllet as skl
from xirang import tools as tl
from xirang import audit
from xirang import ui
from xirang.agent import Agent
from xirang.config import Config, load_config, provider_presets
from xirang.llm import LLM


LAST_SESSION_NAME = "last"
PROVIDER_NAMES = "|".join(sorted(provider_presets().keys()))


HELP = f"""
Slash commands:
  /help                        show this help
  /persona distill <sentence>  create a persona from one sentence
  /persona refine <brief>      refine current persona
  /persona refine <name> :: <brief> refine a saved persona in place
  /persona fork <brief>        fork current persona into a new one
  /persona fork <name> :: <brief> fork a saved persona
  /persona birth <brief>       create a child persona from current persona
  /persona birth <name> :: <brief> create a child from a saved persona
  /persona mutate <brief>      create a mutated child persona
  /persona mutate <name> :: <brief> mutate a saved persona into a child
  /persona mate <name> :: <brief> current persona and named persona have a child
  /persona mode-add <mode> :: <brief> distill a new mode into current persona
  /persona use <name>          load a saved persona
  /persona mode <name>         switch persona output mode
  /persona modes               list output modes of active persona
  /persona show [name]         show current or named persona details
  /persona lineage [name]      show ancestry chain
  /persona children [name]     show direct children
  /persona family [name]       show family tree
  /persona export [name]       export current/named persona family bundle
  /persona export <name> :: <path> export family bundle to a path
  /persona import <path>       import a persona family bundle
  /persona status              show active persona + current mode
  /persona off                 disable active persona
  /persona list                list saved personas
  /memory add <name> :: <body> save a memory
  /memory rule <name> :: <body> save a persistent user rule
  /memory list                 show memory index
  /memory rules                show persistent user rules
  /memory search <query>       search recalled memory candidates
  /memory status               show layered memory counts
  /memory recent [N]           show recent continuity memories
  /memory forget <name>        delete a memory
  /brain [fast|balanced|deep]  show or switch response profile
  /llm                         show provider/model/runtime status
  /llm presets                 list available provider presets
  /llm use <preset>            switch to a provider preset immediately
  /llm model <name>            switch the active model immediately
  /llm provider <name>         switch provider ({PROVIDER_NAMES})
  /catalog [query]             search local API + LLM catalogs
  /catalog api <query>         search public APIs catalog
  /catalog llm <query>         search LLM/provider catalog
  /catalog import api <path>   import public-apis README into local catalog
  /catalog import llm <path>   import free-llm-api README into local catalog
  /cron list                   list local automation jobs
  /cron add <name> :: <schedule> :: <prompt> add a cron-like job
  /cron run <name>             run a named job now
  /cron run-due                run all due jobs now
  /cron delete <name>          delete a job
  /webhook list                list local webhook routes
  /webhook add <name> :: <prompt-prefix> add a webhook route
  /webhook delete <name>       delete a webhook route
  /webhook serve [port]        serve webhook routes in this process
  /bench [dry-run]             run the local benchmark suite
  /recipes                     list cached recipes by hit count
  /skilllets                   list self-grown local skilllets
  /skilllets family            list active persona's own + inherited skill genes
  /skilllets contribute [owner] legacy alias of /genome propose
  /skilllets contribute <owner> :: <path> legacy alias of /genome propose
  /genome propose [owner]      export a sanitized local genome proposal
  /genome propose <owner> :: <path> export genome proposal to a path
  /genome status [owner]       show local gene maturity and risk
  /genome review <path>        inspect a genome proposal before PR/merge
  /skilllets show <name>       show a skilllet markdown file
  /skilllets delete <name>     delete a skilllet
  /mode [default|auto|safe|plan|ask] show or switch permission mode
  /audit [N]                   show recent tool audit events
  /copilot status              show desktop co-pilot session state
  /copilot start [task]        explicitly enable local desktop co-pilot
  /copilot observe [seconds]   bounded screenshot watch of current desktop
  /copilot screenshot [path]   take one explicit desktop screenshot
  /copilot invite <task>       invite Xirang into a live desktop task
  /copilot stop                stop desktop co-pilot for this process
  /session save [name]         save this conversation (default: 'last')
  /session load <name>         restore a saved conversation
  /session status              show current session target
  /session list                list saved sessions
  /session delete <name>       delete a saved session
  /session new                 start a fresh session
  /cost                        show token usage + estimated $ for this session
  /clear                       reset conversation (persona/memory/recipes preserved)
  /exit | /quit                leave (auto-saves as 'last')
"""


# ---------- commands ----------

def _register_subagent(cfg: Config) -> None:
    tl.set_subagent_factory(lambda: Agent(cfg, use_recipes=False))


def _parse_name_and_path(arg: str) -> tuple[str, str]:
    if "::" in arg:
        left, right = arg.split("::", 1)
        return left.strip(), right.strip()
    return arg.strip(), ""


def _parse_multi(arg: str, expected: int) -> list[str]:
    parts = [part.strip() for part in arg.split("::")]
    if len(parts) < expected:
        return []
    return parts[:expected]


def _cmd_persona(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=1)
    if not parts:
        ui.info("usage: /persona distill|refine|fork|birth|mutate|mate|mode-add|use|mode|modes|show|lineage|children|family|export|import|status|off|list")
        return
    sub, arg = parts[0], parts[1] if len(parts) > 1 else ""
    if sub == "distill":
        if not arg:
            ui.warn("give me a sentence describing the persona")
            return
        ui.status("distilling persona — this calls the LLM once...")
        try:
            p = per.distill(agent.llm, arg)
        except Exception as e:
            ui.error(f"distillation failed: {e}")
            return
        per.save(agent.cfg.personas_dir, p)
        agent.persona = p
        agent.persona_mode = "default"
        ui.success(f"persona '{p.name}' saved and activated")
        ui.markdown(f"**Essence:** {p.essence}")
    elif sub == "refine":
        target = agent.persona
        instruction = arg.strip()
        if "::" in arg:
            name, instruction = arg.split("::", 1)
            target = per.load(agent.cfg.personas_dir, name.strip())
            instruction = instruction.strip()
        if not target:
            ui.warn("activate a persona first or use: /persona refine <name> :: <brief>")
            return
        if not instruction:
            ui.warn("usage: /persona refine <brief> OR /persona refine <name> :: <brief>")
            return
        ui.status(f"refining persona '{target.name}'...")
        try:
            refined = per.refine(agent.llm, target, instruction)
        except Exception as e:
            ui.error(f"persona refinement failed: {e}")
            return
        per.save(agent.cfg.personas_dir, refined)
        if agent.persona and agent.persona.slug == target.slug:
            agent.persona = refined
        ui.success(f"persona '{refined.name}' refined and saved")
        ui.markdown(f"**Essence:** {refined.essence}")
    elif sub == "fork":
        target = agent.persona
        instruction = arg.strip()
        if "::" in arg:
            name, instruction = arg.split("::", 1)
            target = per.load(agent.cfg.personas_dir, name.strip())
            instruction = instruction.strip()
        if not target:
            ui.warn("activate a persona first or use: /persona fork <name> :: <brief>")
            return
        if not instruction:
            ui.warn("usage: /persona fork <brief> OR /persona fork <name> :: <brief>")
            return
        ui.status(f"forking persona '{target.name}'...")
        try:
            forked = per.fork(agent.llm, target, instruction)
        except Exception as e:
            ui.error(f"persona fork failed: {e}")
            return
        per.save(agent.cfg.personas_dir, forked)
        agent.persona = forked
        agent.persona_mode = "default"
        ui.success(f"forked persona '{forked.name}' saved and activated")
        ui.markdown(f"**Essence:** {forked.essence}")
    elif sub == "birth":
        target = agent.persona
        instruction = arg.strip()
        if "::" in arg:
            name, instruction = arg.split("::", 1)
            target = per.load(agent.cfg.personas_dir, name.strip())
            instruction = instruction.strip()
        if not target:
            ui.warn("activate a persona first or use: /persona birth <name> :: <brief>")
            return
        if not instruction:
            ui.warn("usage: /persona birth <brief> OR /persona birth <name> :: <brief>")
            return
        ui.status(f"birthing child persona from '{target.name}'...")
        try:
            child = per.birth(agent.llm, target, instruction)
        except Exception as e:
            ui.error(f"persona birth failed: {e}")
            return
        per.save(agent.cfg.personas_dir, child)
        agent.persona = child
        agent.persona_mode = "default"
        ui.success(f"child persona '{child.name}' saved and activated")
        ui.markdown(f"**Essence:** {child.essence}")
    elif sub == "mutate":
        target = agent.persona
        instruction = arg.strip()
        if "::" in arg:
            name, instruction = arg.split("::", 1)
            target = per.load(agent.cfg.personas_dir, name.strip())
            instruction = instruction.strip()
        if not target:
            ui.warn("activate a persona first or use: /persona mutate <name> :: <brief>")
            return
        if not instruction:
            ui.warn("usage: /persona mutate <brief> OR /persona mutate <name> :: <brief>")
            return
        ui.status(f"mutating persona '{target.name}' into a child variant...")
        try:
            child = per.mutate(agent.llm, target, instruction)
        except Exception as e:
            ui.error(f"persona mutation failed: {e}")
            return
        per.save(agent.cfg.personas_dir, child)
        agent.persona = child
        agent.persona_mode = "default"
        ui.success(f"mutated child persona '{child.name}' saved and activated")
        ui.markdown(f"**Essence:** {child.essence}")
    elif sub == "mate":
        if "::" not in arg:
            ui.warn("usage: /persona mate <partner> :: <child brief>")
            return
        if not agent.persona:
            ui.warn("activate one parent first: /persona use <name>")
            return
        partner_name, instruction = arg.split("::", 1)
        partner = per.load(agent.cfg.personas_dir, partner_name.strip())
        instruction = instruction.strip()
        if not partner:
            ui.warn(f"no persona named '{partner_name.strip()}'")
            return
        if not instruction:
            ui.warn("usage: /persona mate <partner> :: <child brief>")
            return
        ui.status(f"matching '{agent.persona.name}' with '{partner.name}'...")
        try:
            child = per.mate(agent.llm, agent.persona, partner, instruction)
        except Exception as e:
            ui.error(f"persona mating failed: {e}")
            return
        per.save(agent.cfg.personas_dir, child)
        agent.persona = child
        agent.persona_mode = "default"
        ui.success(f"family child '{child.name}' saved and activated")
        ui.markdown(f"**Essence:** {child.essence}")
    elif sub == "mode-add":
        if not agent.persona:
            ui.warn("activate a persona first: /persona use <name>")
            return
        if "::" not in arg:
            ui.warn("usage: /persona mode-add <mode> :: <brief>")
            return
        mode_name, instruction = arg.split("::", 1)
        mode_name, instruction = mode_name.strip(), instruction.strip()
        if not mode_name or not instruction:
            ui.warn("usage: /persona mode-add <mode> :: <brief>")
            return
        ui.status(f"distilling mode '{mode_name}' into persona '{agent.persona.name}'...")
        try:
            updated = per.add_mode(agent.llm, agent.persona, mode_name, instruction)
        except Exception as e:
            ui.error(f"mode distillation failed: {e}")
            return
        per.save(agent.cfg.personas_dir, updated)
        agent.persona = updated
        ui.success(f"persona mode '{mode_name}' added")
    elif sub == "use":
        p = per.load(agent.cfg.personas_dir, arg)
        if not p:
            ui.error(f"no persona named '{arg}'")
            return
        agent.persona = p
        agent.persona_mode = "default"
        ui.success(f"persona '{p.name}' activated")
    elif sub == "mode":
        if not agent.persona:
            ui.warn("activate a persona first: /persona use <name>")
            return
        if not arg:
            ui.warn("usage: /persona mode <name>")
            return
        modes = agent.persona.style_modes or {"default": "natural baseline voice"}
        if arg not in modes:
            ui.warn(f"unknown mode: {arg}. available: {', '.join(modes)}")
            return
        agent.persona_mode = arg
        ui.success(f"persona mode switched to '{arg}'")
    elif sub == "modes":
        if not agent.persona:
            ui.warn("activate a persona first: /persona use <name>")
            return
        modes = agent.persona.style_modes or {"default": "natural baseline voice"}
        current = agent.persona_mode or "default"
        ui.markdown(
            "**Persona modes:**\n"
            + "\n".join(f"- `{name}`{' ← current' if name == current else ''}: {desc}" for name, desc in modes.items())
        )
    elif sub == "show":
        target = agent.persona if not arg else per.load(agent.cfg.personas_dir, arg)
        if not target:
            ui.warn(f"no persona named '{arg or 'current'}'")
            return
        active_mode = agent.persona_mode if agent.persona and target.slug == agent.persona.slug else "default"
        ui.markdown(target.to_system_augmentation(active_mode))
    elif sub == "lineage":
        target = agent.persona if not arg else per.load(agent.cfg.personas_dir, arg)
        if not target:
            ui.warn(f"no persona named '{arg or 'current'}'")
            return
        chain = per.lineage(agent.cfg.personas_dir, target)
        ui.markdown("**Persona lineage**\n" + "\n".join(f"- `{item.slug}` · {item.name}" for item in chain))
    elif sub == "children":
        target = agent.persona if not arg else per.load(agent.cfg.personas_dir, arg)
        if not target:
            ui.warn(f"no persona named '{arg or 'current'}'")
            return
        children = per.children_of(agent.cfg.personas_dir, target.slug)
        if not children:
            ui.info(f"'{target.name}' has no children yet")
            return
        ui.markdown("**Persona children**\n" + "\n".join(f"- `{item.slug}` · {item.name}" for item in children))
    elif sub == "family":
        target = agent.persona if not arg else per.load(agent.cfg.personas_dir, arg)
        if not target:
            ui.warn(f"no persona named '{arg or 'current'}'")
            return
        ui.markdown(per.family_tree(agent.cfg.personas_dir, target.slug))
    elif sub == "export":
        name_arg, path_arg = _parse_name_and_path(arg)
        target = agent.persona
        if name_arg:
            maybe_path = Path(name_arg).expanduser()
            if maybe_path.suffix == ".json" or "/" in name_arg:
                path_arg = name_arg
            else:
                target = per.load(agent.cfg.personas_dir, name_arg)
        if not target:
            ui.warn("activate a persona first or use: /persona export <name>")
            return
        try:
            fp = bun.export_family_bundle(
                agent.cfg.home,
                agent.cfg.personas_dir,
                agent.cfg.skilllets_dir,
                target.slug,
                output_path=Path(path_arg).expanduser() if path_arg else None,
            )
        except Exception as e:
            ui.error(f"persona export failed: {e}")
            return
        ui.success(f"family bundle exported: {fp}")
    elif sub == "import":
        bundle_path = Path(arg.strip()).expanduser() if arg.strip() else None
        if not bundle_path:
            ui.warn("usage: /persona import <path>")
            return
        try:
            result = bun.import_family_bundle(agent.cfg.personas_dir, agent.cfg.skilllets_dir, bundle_path)
        except Exception as e:
            ui.error(f"persona import failed: {e}")
            return
        ui.success(f"family bundle imported for '{result['target_slug']}'")
        ui.markdown(
            "\n".join(
                [
                    "**Import result**",
                    f"- personas_saved: {result['personas_saved']}",
                    f"- personas_skipped: {result['personas_skipped']}",
                    f"- skilllets_saved: {result['skilllets_saved']}",
                    f"- skilllets_skipped: {result['skilllets_skipped']}",
                ]
            )
        )
    elif sub == "status":
        if not agent.persona:
            ui.info("no active persona")
            return
        current = agent.persona_mode or "default"
        ui.markdown(
            "\n".join(
                [
                    "**Active persona**",
                    f"- name: `{agent.persona.name}`",
                    f"- mode: `{current}`",
                    f"- essence: {agent.persona.essence}",
                    f"- family: `{agent.persona.family_name or '-'}'",
                    f"- parent: `{agent.persona.parent_slug or '-'}'",
                    f"- co-parent: `{agent.persona.other_parent_slug or '-'}'",
                    f"- refinements: {len(agent.persona.refinement_notes)}",
                ]
            )
        )
    elif sub == "off":
        agent.persona = None
        agent.persona_mode = None
        ui.success("persona disabled")
    elif sub == "list":
        names = per.list_all(agent.cfg.personas_dir)
        if not names:
            ui.info("no personas saved yet. use: /persona distill <sentence>")
        else:
            ui.markdown("**Saved personas:**\n" + "\n".join(f"- {n}" for n in names))
    else:
        ui.warn(f"unknown subcommand: {sub}")


def _cmd_memory(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=1)
    if not parts:
        ui.info("usage: /memory add <name> :: <body> | rule <name> :: <body> | list | rules | search <query> | recent [N] | status | forget <name>")
        return
    sub, arg = parts[0], parts[1] if len(parts) > 1 else ""
    if sub == "add":
        if "::" not in arg:
            ui.warn("format: /memory add <name> :: <body>")
            return
        name, body = arg.split("::", 1)
        name, body = name.strip(), body.strip()
        fp = mem.save_memory(agent.cfg.memory_dir, name=name, description=body[:100],
                             mem_type="user", body=body)
        ui.success(f"memory saved: {fp.name}")
    elif sub == "rule":
        if "::" not in arg:
            ui.warn("format: /memory rule <name> :: <body>")
            return
        name, body = arg.split("::", 1)
        name, body = name.strip(), body.strip()
        fp = mem.save_rule(agent.cfg.memory_dir, name=name, body=body)
        ui.success(f"persistent rule saved: {fp.name}")
    elif sub == "list":
        idx = mem.load_index(agent.cfg.memory_dir)
        ui.markdown(idx) if idx else ui.info("no memories yet")
    elif sub == "rules":
        rows = mem.persistent_rules(agent.cfg.memory_dir, limit=12)
        if not rows:
            ui.info("no persistent user rules yet")
            return
        lines = ["**Persistent user rules**"]
        for record in rows:
            updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(record.updated_at))
            lines.append(f"- `{record.name}` · {updated} · {record.description}")
        ui.markdown("\n".join(lines))
    elif sub == "search":
        if not arg:
            ui.warn("usage: /memory search <query>")
            return
        hits = mem.search(agent.cfg.memory_dir, arg, limit=8)
        if not hits:
            ui.info("no matching memories")
            return
        lines = [f"**Memory matches** for `{arg}`:"]
        for score, record in hits:
            lines.append(
                f"- `{record.layer}` · `{record.name}` · score={score:.2f} · {record.description or record.type}"
            )
        ui.markdown("\n".join(lines))
    elif sub == "status":
        counts = mem.stats(agent.cfg.memory_dir)
        lines = ["**Layered memory status**"]
        for layer in ("prelude", "recurrent", "coda", "archive"):
            lines.append(f"- `{layer}`: {counts.get(layer, 0)}")
        lines.append(f"- `total`: {counts.get('total', 0)}")
        ui.markdown("\n".join(lines))
    elif sub == "recent":
        try:
            limit = int(arg.strip() or "8")
        except ValueError:
            limit = 8
        rows = mem.recent(agent.cfg.memory_dir, limit=limit, layers=("recurrent", "coda"))
        if not rows:
            ui.info("no recent memory yet")
            return
        lines = ["**Recent continuity memory**"]
        for record in rows:
            updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(record.updated_at))
            lines.append(f"- `{record.layer}` · `{record.name}` · {updated} · {record.description}")
        ui.markdown("\n".join(lines))
    elif sub == "forget":
        ok = mem.forget(agent.cfg.memory_dir, arg)
        (ui.success if ok else ui.warn)(f"{'removed' if ok else 'not found'}: {arg}")
    else:
        ui.warn(f"unknown subcommand: {sub}")


def _cmd_recipes(cfg: Config) -> None:
    recipes = rcp.list_all(cfg.recipes_path)
    if not recipes:
        ui.info("no recipes yet — Xirang learns as you use it")
        return
    lines = ["**Cached recipes** (by hits):"]
    for r in recipes[:30]:
        tools_seq = " → ".join(s.get("tool", "?") for s in r.steps)
        lines.append(f"- `{r.hit_count}×` {r.intent_sample[:60]} :: {tools_seq}")
    ui.markdown("\n".join(lines))


def _cmd_skilllets(agent: Agent, rest: str) -> None:
    cfg = agent.cfg
    parts = rest.strip().split(maxsplit=1)
    sub = parts[0] if parts else "list"
    arg = parts[1] if len(parts) > 1 else ""

    if sub in ("list", ""):
        items = skl.list_all(cfg.skilllets_dir)
        if not items:
            ui.info("no skilllets yet — complete tool-using tasks and Xirang will grow them")
            return
        lines = ["**Self-grown skilllets** (local markdown workflows):"]
        for item in items[:30]:
            lines.append(f"- `{item.slug}` · {item.hit_count}× · {item.fingerprint} :: {item.tool_chain}")
        ui.markdown("\n".join(lines))
        return

    if sub == "family":
        if not agent.persona:
            ui.warn("activate a persona first: /persona use <name>")
            return
        rendered = skl.render_family_index(cfg.skilllets_dir, cfg.personas_dir, agent.persona.slug)
        if not rendered:
            ui.info("no family skill genes yet — let this persona solve tasks first")
            return
        ui.markdown(rendered)
        return

    if sub == "contribute":
        _cmd_genome(agent, f"propose {arg}".strip())
        return

    if sub == "show":
        if not arg:
            ui.warn("usage: /skilllets show <name>")
            return
        for item in skl.list_all(cfg.skilllets_dir):
            if item.slug == arg or item.name == arg:
                fp = cfg.skilllets_dir / f"{item.slug}.md"
                ui.markdown(fp.read_text(encoding="utf-8"))
                return
        ui.warn(f"not found: {arg}")
        return

    if sub == "delete":
        if not arg:
            ui.warn("usage: /skilllets delete <name>")
            return
        ok = skl.delete(cfg.skilllets_dir, arg)
        (ui.success if ok else ui.warn)(f"{'deleted' if ok else 'not found'}: {arg}")
        return

    ui.warn("usage: /skilllets [list] | family | contribute [owner] | show <name> | delete <name>")


def _cmd_genome(agent: Agent, rest: str) -> None:
    cfg = agent.cfg
    parts = rest.strip().split(maxsplit=1)
    if not parts:
        ui.info("usage: /genome propose [owner] | status [owner] | review <path>")
        return
    sub = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if sub == "propose":
        owner_arg, path_arg = _parse_name_and_path(arg)
        owner_slug = ""
        if owner_arg:
            maybe_path = Path(owner_arg).expanduser()
            if maybe_path.suffix == ".json" or "/" in owner_arg:
                path_arg = owner_arg
            else:
                owner_slug = owner_arg
        elif agent.persona:
            owner_slug = agent.persona.slug
        try:
            fp = bun.export_genome_proposal(
                cfg.home,
                cfg.skilllets_dir,
                owner_slug=owner_slug,
                output_path=Path(path_arg).expanduser() if path_arg else None,
            )
        except Exception as e:
            ui.error(f"genome proposal export failed: {e}")
            return
        scope = owner_slug or "all local owners"
        ui.success(f"genome proposal exported: {fp}")
        ui.info(f"proposal scope: {scope}")
        ui.info("review it locally, then commit/push manually if you want this gene to flow upstream")
        return

    if sub == "status":
        owner_slug = arg.strip()
        if not owner_slug and agent.persona:
            owner_slug = agent.persona.slug
        items = skl.list_all(cfg.skilllets_dir)
        if owner_slug:
            items = [item for item in items if item.owner_slug == owner_slug]
        if not items:
            scope = owner_slug or "all local owners"
            ui.info(f"no local genes found for {scope}")
            return
        lines = [f"**Local genome status** ({owner_slug or 'all local owners'})"]
        for item in items[:30]:
            maturity = bun.gene_maturity(item)
            lines.append(
                f"- `{item.slug}` · {maturity['level']} · score={maturity['score']} · "
                f"risk={maturity['risk']} · ok={item.success_count}/fail={item.failure_count} · {item.fingerprint}"
            )
        ui.markdown("\n".join(lines))
        return

    if sub == "review":
        bundle_path = Path(arg.strip()).expanduser() if arg.strip() else None
        if not bundle_path:
            ui.warn("usage: /genome review <path>")
            return
        try:
            report = bun.review_genome_proposal(bundle_path)
        except Exception as e:
            ui.error(f"genome review failed: {e}")
            return
        lines = [
            "**Genome proposal review**",
            f"- bundle: `{report['bundle_path']}`",
            f"- type: `{report['bundle_type']}`",
            f"- owner: `{report['owner_slug'] or '-'}`",
            f"- accepted: {report['accepted_count']}",
            f"- rejected: {report['rejected_count']}",
            f"- stable_or_proven: {report['mature_count']}",
            f"- high_risk: {report['high_risk_count']}",
        ]
        for item in report["accepted_skilllets"][:8]:
            maturity = item.get("maturity", {})
            lines.append(
                f"- accepted gene: `{item['slug']}` · {maturity.get('level', '?')} · "
                f"risk={maturity.get('risk', '?')} :: {item['fingerprint']}"
            )
        for item in report["rejected_skilllets"][:8]:
            lines.append(f"- rejected gene: `{item['slug'] or '-'}` :: {item['reason']}")
        ui.markdown("\n".join(lines))
        return

    ui.warn("usage: /genome propose [owner] | status [owner] | review <path>")


def _cmd_mode(agent: Agent, rest: str) -> None:
    arg = rest.strip().lower()
    if not arg:
        ui.info(f"current mode: {agent.cfg.mode} (default|auto|safe|plan|ask)")
        return
    if arg not in {"default", "auto", "safe", "plan", "ask"}:
        ui.warn("usage: /mode default|auto|safe|plan|ask")
        return
    agent.cfg.mode = arg
    ui.success(f"permission mode switched to '{arg}'")


def _cmd_brain(agent: Agent, rest: str) -> None:
    arg = rest.strip().lower()
    if not arg:
        ui.markdown(
            "\n".join(
                [
                    "**Brain profile**",
                    f"- profile: `{agent.cfg.response_profile}`",
                    f"- max_output_tokens: {agent.cfg.max_output_tokens}",
                    f"- max_tool_iters: {agent.cfg.max_tool_iters}",
                ]
            )
        )
        return
    try:
        profile = agent.set_response_profile(arg)
    except Exception as e:
        ui.warn(str(e))
        return
    ui.success(
        f"profile switched to '{profile}' · max_output_tokens={agent.cfg.max_output_tokens} · max_tool_iters={agent.cfg.max_tool_iters}"
    )


def _cmd_llm(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts and parts[0] else "status"
    arg = parts[1] if len(parts) > 1 else ""
    if sub in {"", "status"}:
        runtime = agent.runtime_status()
        lines = [
            "**LLM runtime**",
            f"- provider: `{runtime['provider']}`",
            f"- model: `{runtime['model']}`",
            f"- profile: `{runtime['profile']}`",
            f"- mode: `{runtime['mode']}`",
            f"- session: `{runtime['session']}`",
        ]
        ui.markdown("\n".join(lines))
        return
    if sub == "presets":
        presets = provider_presets()
        lines = ["**LLM presets**"]
        for name, preset in presets.items():
            lines.append(
                f"- `{name}` · client={preset['client']} · model={preset['default_model']} · "
                f"base_url={preset['default_base_url'] or '-'}"
            )
        ui.markdown("\n".join(lines))
        return
    if sub == "use":
        if not arg:
            ui.warn("usage: /llm use <preset>")
            return
        try:
            agent.switch_provider(arg)
        except Exception as e:
            ui.error(str(e))
            return
        ui.success(f"provider preset switched to '{agent.cfg.provider}' with model '{agent.cfg.model}'")
        return
    if sub == "model":
        if not arg:
            ui.warn("usage: /llm model <name>")
            return
        try:
            agent.switch_model(arg)
        except Exception as e:
            ui.error(str(e))
            return
        ui.success(f"model switched to '{agent.cfg.model}'")
        return
    if sub == "provider":
        if not arg:
            ui.warn(f"usage: /llm provider <{PROVIDER_NAMES}>")
            return
        try:
            agent.switch_provider(arg)
        except Exception as e:
            ui.error(str(e))
            return
        ui.success(f"provider switched to '{agent.cfg.provider}' with model '{agent.cfg.model}'")
        return
    ui.warn("usage: /llm | /llm presets | /llm use <preset> | /llm model <name> | /llm provider <name>")


def _cmd_catalog(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=2)
    if not parts or not parts[0]:
        ui.markdown(cat.format_entries(cat.search(agent.cfg.catalogs_dir, query="", kind="all", limit=10)))
        return
    sub = parts[0].lower()
    if sub in {"api", "llm", "all"}:
        query = parts[1] if len(parts) > 1 else ""
        ui.markdown(cat.format_entries(cat.search(agent.cfg.catalogs_dir, query=query, kind=sub, limit=12)))
        return
    if sub == "import":
        if len(parts) < 3:
            ui.warn("usage: /catalog import <api|llm> <path>")
            return
        kind, path = parts[1].lower(), parts[2].strip()
        try:
            fp, count = cat.import_catalog(agent.cfg.catalogs_dir, kind, Path(path).expanduser())
        except Exception as e:
            ui.error(f"catalog import failed: {e}")
            return
        ui.success(f"imported {count} {kind} catalog entries into {fp}")
        return
    query = rest.strip()
    ui.markdown(cat.format_entries(cat.search(agent.cfg.catalogs_dir, query=query, kind="all", limit=12)))


def _cmd_cron(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts and parts[0] else "list"
    arg = parts[1] if len(parts) > 1 else ""
    if sub in {"", "list"}:
        jobs = auto.list_jobs(agent.cfg.home)
        if not jobs:
            ui.info("no cron jobs yet")
            return
        lines = ["**Automation jobs**"]
        for job in jobs:
            next_run = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job.next_run_at)) if job.next_run_at else "-"
            lines.append(
                f"- `{job.name}` · {job.schedule} · next={next_run} · session={job.session_name} · enabled={job.enabled}"
            )
        ui.markdown("\n".join(lines))
        return
    if sub == "add":
        items = _parse_multi(arg, 3)
        if not items:
            ui.warn("usage: /cron add <name> :: <schedule> :: <prompt>")
            return
        name, schedule, prompt = items
        try:
            job = auto.add_job(agent.cfg.home, name, schedule, prompt)
        except Exception as e:
            ui.error(f"cron add failed: {e}")
            return
        ui.success(f"cron job '{job.name}' saved")
        ui.info(f"next run at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(job.next_run_at))}")
        return
    if sub == "run":
        if not arg:
            ui.warn("usage: /cron run <name>")
            return
        try:
            result = auto.run_job(agent.cfg, arg.strip())
        except Exception as e:
            ui.error(f"cron run failed: {e}")
            return
        ui.success(f"cron job '{result['job']}' executed")
        if result.get("output"):
            ui.markdown(result["output"])
        return
    if sub == "run-due":
        results = auto.run_due_jobs(agent.cfg)
        if not results:
            ui.info("no due jobs")
            return
        lines = ["**Due job results**"]
        for item in results:
            lines.append(f"- `{item['job']}` · success={item['success']} · session={item['session']}")
        ui.markdown("\n".join(lines))
        return
    if sub == "delete":
        if not arg:
            ui.warn("usage: /cron delete <name>")
            return
        ok = auto.delete_job(agent.cfg.home, arg.strip())
        (ui.success if ok else ui.warn)(f"{'deleted' if ok else 'not found'}: {arg.strip()}")
        return
    ui.warn("usage: /cron list | add <name> :: <schedule> :: <prompt> | run <name> | run-due | delete <name>")


def _cmd_webhook(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts and parts[0] else "list"
    arg = parts[1] if len(parts) > 1 else ""
    if sub in {"", "list"}:
        routes = auto.load_routes(agent.cfg.home)
        if not routes:
            ui.info("no webhook routes yet")
            return
        lines = ["**Webhook routes**"]
        for route in routes:
            lines.append(
                f"- `{route.name}` · token=`{route.token}` · session=`{route.session_name}` · "
                f"last_used={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(route.last_used_at)) if route.last_used_at else '-'}"
            )
        ui.markdown("\n".join(lines))
        return
    if sub == "add":
        items = _parse_multi(arg, 2)
        if not items:
            ui.warn("usage: /webhook add <name> :: <prompt-prefix>")
            return
        name, prompt_prefix = items
        route = auto.add_route(agent.cfg.home, name, prompt_prefix=prompt_prefix)
        ui.success(f"webhook route '{route.name}' saved")
        ui.info(f"POST http://127.0.0.1:8765/hook/{route.name}?token={route.token}")
        return
    if sub == "delete":
        if not arg:
            ui.warn("usage: /webhook delete <name>")
            return
        ok = auto.delete_route(agent.cfg.home, arg.strip())
        (ui.success if ok else ui.warn)(f"{'deleted' if ok else 'not found'}: {arg.strip()}")
        return
    if sub == "serve":
        host = "127.0.0.1"
        port = 8765
        raw = arg.strip()
        if raw:
            if ":" in raw:
                host, port_str = raw.rsplit(":", 1)
                port = int(port_str)
            else:
                port = int(raw)
        ui.status(f"serving webhooks on http://{host}:{port}")
        auto.serve_webhooks(agent.cfg, host=host, port=port)
        return
    ui.warn("usage: /webhook list | add <name> :: <prompt-prefix> | delete <name> | serve [host:port]")


def _cmd_bench(agent: Agent, rest: str) -> None:
    dry_run = rest.strip().lower() in {"dry-run", "--dry-run", "dry"}
    out_path = agent.cfg.home / "bench_results.json"
    ui.status("running benchmark suite..." + (" (dry-run)" if dry_run else ""))
    report = bench.run_benchmark(agent.cfg, dry_run=dry_run, out_path=out_path)
    if dry_run:
        ui.markdown(
            "\n".join(
                ["**Benchmark dry-run**", f"- tasks: {report['task_count']}", f"- output: `{out_path}`"]
                + [f"- `{item['name']}` · {item['description']}" for item in report["tasks"]]
            )
        )
        return
    lines = [
        "**Benchmark results**",
        f"- passed: {report['passed']}/{report['task_count']}",
        f"- failed: {report['failed']}",
        f"- output: `{out_path}`",
    ]
    for item in report["results"]:
        lines.append(f"- `{item['name']}` · passed={item['passed']} · {item['detail']}")
    ui.markdown("\n".join(lines))


def _cmd_audit(cfg: Config, rest: str) -> None:
    try:
        limit = int(rest.strip() or "20")
    except ValueError:
        limit = 20
    rows = audit.tail(cfg.audit_path, limit=limit)
    if not rows:
        ui.info("no audit events yet")
        return
    lines = ["**Recent audit events:**"]
    for row in rows:
        event = row.get("event", "?")
        tool = row.get("tool", "")
        allowed = row.get("allowed", "")
        reason = row.get("reason", "")
        risk = row.get("risk", "")
        lines.append(f"- `{event}` tool={tool} allowed={allowed} risk={risk} {reason}")
    ui.markdown("\n".join(lines))


def _format_copilot_status(data: dict) -> str:
    desktop_state = data.get("desktop", {}) if isinstance(data.get("desktop"), dict) else {}
    lines = [
        "**Desktop co-pilot**",
        f"- active: `{bool(data.get('active'))}`",
        f"- task: {data.get('task') or '-'}",
        f"- state: `{data.get('state_path', '-')}`",
        f"- env: `{desktop_state.get('env', 'XIRANG_DESKTOP_ENABLE')}`",
        f"- desktop_enabled: `{desktop_state.get('enabled', False)}`",
        f"- pyautogui: `{desktop_state.get('pyautogui_available', False)}`",
    ]
    if desktop_state.get("screen_size"):
        lines.append(f"- screen: `{desktop_state['screen_size']}`")
    if desktop_state.get("cursor"):
        lines.append(f"- cursor: `{desktop_state['cursor']}`")
    if desktop_state.get("error"):
        lines.append(f"- note: {desktop_state['error']}")
    return "\n".join(lines)


def _cmd_copilot(agent: Agent, rest: str) -> None:
    parts = rest.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else "status"
    arg = parts[1] if len(parts) > 1 else ""

    if sub in {"", "status"}:
        ui.markdown(_format_copilot_status(co.status(agent.cfg.home)))
        return

    if sub == "start":
        data = co.start(agent.cfg.home, arg)
        ui.success("desktop co-pilot enabled for this Xirang process")
        ui.info("This is explicit opt-in: no background keylogger, no hidden monitoring, no auto-upload.")
        ui.markdown(_format_copilot_status(data))
        return

    if sub == "stop":
        data = co.stop(agent.cfg.home)
        ui.success("desktop co-pilot stopped for this Xirang process")
        ui.markdown(_format_copilot_status(data))
        return

    if sub == "observe":
        try:
            seconds = float(arg.strip() or "3")
        except ValueError:
            seconds = 3.0
        ui.status("observing desktop with bounded screenshots...")
        ui.markdown(co.observe(agent.cfg.home, seconds=seconds))
        return

    if sub == "screenshot":
        ui.status("taking one explicit desktop screenshot...")
        ui.markdown(co.screenshot(agent.cfg.home, path=arg.strip()))
        return

    if sub == "invite":
        task = arg.strip()
        if not task:
            ui.warn("usage: /copilot invite <task>")
            return
        state = co.status(agent.cfg.home)
        if not state.get("active"):
            co.start(agent.cfg.home, task)
            ui.status("co-pilot session started for this invitation")
        observation = co.screenshot(agent.cfg.home)
        prompt = co.invitation_prompt(task, observation=observation)
        agent.turn(prompt)
        return

    ui.warn("usage: /copilot status|start [task]|observe [seconds]|screenshot [path]|invite <task>|stop")


def _cmd_session(agent: Agent, rest: str) -> Agent:
    """Handle /session subcommands. Returns the (possibly new) agent."""
    parts = rest.strip().split(maxsplit=1)
    if not parts:
        ui.info("usage: /session save [name] | load <name> | status | list | delete <name> | new")
        return agent
    sub, arg = parts[0], parts[1] if len(parts) > 1 else ""
    if sub == "save":
        name = arg or LAST_SESSION_NAME
        fp = sess.save(agent.cfg.home, name, agent)
        agent.current_session_name = name
        agent.last_saved_at = time.time()
        ui.success(f"session saved: {fp.name} ({agent.turn_count} turns)")
    elif sub == "load":
        if not arg:
            ui.warn("usage: /session load <name>")
            return agent
        blob = sess.load(agent.cfg.home, arg)
        if not blob:
            ui.error(f"no session named '{arg}'")
            return agent
        sess.apply_to_agent(blob, agent)
        agent.current_session_name = arg
        ui.success(
            f"loaded '{arg}': {blob.turn_count} turns, "
            f"{len(agent.messages)} messages"
            + (f", persona: {blob.persona_slug}" if blob.persona_slug else "")
            + (f", mode: {blob.persona_mode}" if blob.persona_mode else "")
        )
    elif sub == "status":
        saved = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(agent.last_saved_at)) if agent.last_saved_at else "not yet"
        ui.markdown(
            "\n".join(
                [
                    "**Session status**",
                    f"- current target: `{agent.current_session_name}`",
                    f"- turns: {agent.turn_count}",
                    f"- last autosave: {saved}",
                ]
            )
        )
    elif sub == "list":
        rows = sess.list_sessions(agent.cfg.home)
        if not rows:
            ui.info("no saved sessions")
        else:
            lines = ["**Saved sessions:**"]
            for r in rows:
                persona_str = f" [persona:{r['persona']}]" if r["persona"] else ""
                mode_str = f" [mode:{r['mode']}]" if r.get("mode") else ""
                lines.append(
                    f"- `{r['name']}` · {r['turns']} turns · "
                    f"{r['saved']} · {r['model']}{persona_str}{mode_str}"
                )
            ui.markdown("\n".join(lines))
    elif sub == "delete":
        if not arg:
            ui.warn("usage: /session delete <name>")
            return agent
        ok = sess.delete(agent.cfg.home, arg)
        (ui.success if ok else ui.warn)(f"{'deleted' if ok else 'not found'}: {arg}")
    elif sub == "new":
        agent.clear()
        agent.current_session_name = LAST_SESSION_NAME
        ui.success("fresh session started")
    else:
        ui.warn(f"unknown subcommand: {sub}")
    return agent


def _cmd_cost(agent: Agent) -> None:
    u = agent.total_usage
    cost = pricing.compute_cost(u, agent.cfg.model)
    in_price, out_price = pricing.lookup(agent.cfg.model)
    lines = [
        f"**Session cost** (model `{agent.cfg.model}` @ ${in_price}/${out_price} per 1M)",
        f"- input tokens:      {u.get('input', 0):,}",
        f"- output tokens:     {u.get('output', 0):,}",
        f"- cache_read:        {u.get('cache_read', 0):,}",
        f"- cache_create:      {u.get('cache_create', 0):,}",
        f"- turns:             {agent.turn_count}",
        f"- **estimated cost**: {pricing.format_cost(cost)}",
    ]
    ui.markdown("\n".join(lines))


def _handle_command(cmd: str, agent: Agent) -> tuple[bool, Agent]:
    """Return (keep_looping, agent)."""
    raw = cmd[1:].strip()
    name, _, rest = raw.partition(" ")
    if name in ("exit", "quit"):
        return False, agent
    if name == "help":
        ui.markdown(HELP)
    elif name == "persona":
        _cmd_persona(agent, rest)
    elif name == "memory":
        _cmd_memory(agent, rest)
    elif name == "recipes":
        _cmd_recipes(agent.cfg)
    elif name == "skilllets":
        _cmd_skilllets(agent, rest)
    elif name == "genome":
        _cmd_genome(agent, rest)
    elif name == "mode":
        _cmd_mode(agent, rest)
    elif name == "brain":
        _cmd_brain(agent, rest)
    elif name == "llm":
        _cmd_llm(agent, rest)
    elif name == "catalog":
        _cmd_catalog(agent, rest)
    elif name == "cron":
        _cmd_cron(agent, rest)
    elif name == "webhook":
        _cmd_webhook(agent, rest)
    elif name == "bench":
        _cmd_bench(agent, rest)
    elif name == "audit":
        _cmd_audit(agent.cfg, rest)
    elif name == "copilot":
        _cmd_copilot(agent, rest)
    elif name == "session":
        agent = _cmd_session(agent, rest)
    elif name == "cost":
        _cmd_cost(agent)
    elif name == "clear":
        agent.clear()
        ui.success("conversation reset")
    else:
        ui.warn(f"unknown command: /{name} — try /help")
    return True, agent


# ---------- REPL ----------

def _repl(agent: Agent) -> None:
    """Unified REPL. Handles slash commands, sends everything else to agent."""
    hist_file = agent.cfg.home / ".history"
    ptk_session: PromptSession = PromptSession(history=FileHistory(str(hist_file)))
    try:
        while True:
            try:
                line = ptk_session.prompt("▸ ").strip()
            except (KeyboardInterrupt, EOFError):
                ui.info("\nbye.")
                break
            if not line:
                continue
            if line.startswith("/"):
                keep, agent = _handle_command(line, agent)
                if not keep:
                    ui.info("bye.")
                    break
                continue
            agent.turn(line)
    finally:
        # Auto-save 'last' session on exit
        if agent.turn_count > 0:
            try:
                sess.save(agent.cfg.home, agent.current_session_name, agent)
                ui.status(f"auto-saved session as '{agent.current_session_name}'")
            except Exception as e:
                ui.warn(f"auto-save failed: {e}")


def _build_agent(cfg: Config, persona_name: str | None = None,
                 resume: str | None = None) -> Agent:
    _register_subagent(cfg)
    agent = Agent(cfg)
    agent.current_session_name = resume or LAST_SESSION_NAME
    if persona_name:
        p = per.load(cfg.personas_dir, persona_name)
        if p:
            agent.persona = p
            agent.persona_mode = "default"
        else:
            ui.warn(f"persona '{persona_name}' not found")
    if resume:
        blob = sess.load(cfg.home, resume)
        if blob:
            sess.apply_to_agent(blob, agent)
            agent.current_session_name = resume
            ui.status(f"resumed session '{resume}': {blob.turn_count} turns")
        else:
            ui.warn(f"no session named '{resume}'")
    return agent


def _setup_home() -> Path:
    return Path(os.environ.get("XIRANG_HOME") or (Path.home() / ".xirang")).expanduser()


def _run_setup(provider: str, api_key: str = "", model: str = "") -> None:
    provider = provider.lower()
    presets = provider_presets()
    if provider not in presets:
        ui.error(f"Unknown provider: {provider}")
        ui.info("Try: xirang --setup openrouter")
        return

    if provider in setup_mod.GUIDES:
        ui.markdown(setup_mod.guide_text(provider))
    preset = presets[provider]
    if preset["requires_api_key"] and not api_key:
        key_env = setup_mod.primary_key_env(provider)
        ui.info(f"Paste your {provider} API key for {key_env}. It will be saved to ~/.xirang/.env")
        api_key = getpass.getpass(f"{key_env}: ").strip()
    try:
        fp = setup_mod.configure_provider(
            _setup_home(),
            provider,
            api_key=api_key,
            model=model,
        )
    except Exception as e:
        ui.error(str(e))
        return

    ui.success(f"setup saved to {fp}")
    ui.info('Next: xirang --doctor')
    ui.info('Then: xirang --doctor-live')


def _run_doctor(cfg: Config) -> None:
    ui.markdown("**Xirang doctor**")
    ui.code(setup_mod.format_doctor(setup_mod.doctor_rows(cfg)), lang="text")
    if cfg.provider_requires_api_key and not cfg.api_key:
        ui.warn(f"Run: xirang --setup {cfg.provider}")
    else:
        ui.success("ready for live provider check: xirang --doctor-live")


def _doctor_live_probe(llm: LLM, greeting: str = "你好") -> str:
    return llm.complete(
        prompt=greeting,
        system="You are a connectivity probe. Reply in one short friendly line.",
        max_tokens=64,
    ).strip()


def _run_doctor_live(cfg: Config) -> bool:
    _run_doctor(cfg)
    if cfg.provider_requires_api_key and not cfg.api_key:
        return False
    ui.status("sending live hello to provider...")
    try:
        reply = _doctor_live_probe(LLM(cfg))
    except Exception as e:
        ui.error(f"live provider check failed: {type(e).__name__}: {e}")
        return False
    if not reply:
        ui.error("live provider check failed: empty response")
        return False
    ui.success("live provider check passed")
    ui.markdown(
        "\n".join(
            [
                "**Live reply**",
                f"- provider: `{cfg.provider}`",
                f"- model: `{cfg.model}`",
                f"- reply: {reply[:240]}",
            ]
        )
    )
    return True


# ---------- main ----------

def main() -> None:
    preset_names = sorted(provider_presets().keys())
    parser = argparse.ArgumentParser(
        prog="xirang", description="Xirang / 息壤 — lightweight self-evolving agent"
    )
    parser.add_argument("--provider", choices=preset_names,
                        help="Override XIRANG_PROVIDER env var")
    parser.add_argument("--model", help="Override model for selected provider")
    parser.add_argument("--setup", nargs="?", const="openrouter", metavar="PROVIDER",
                        help="One-key first-run setup (default: openrouter)")
    parser.add_argument("--api-key", help="API key for non-interactive --setup")
    parser.add_argument("--setup-model", help="Model to save during --setup")
    parser.add_argument("--doctor", action="store_true",
                        help="Check provider, key, model, and local catalogs")
    parser.add_argument("--doctor-live", action="store_true",
                        help="Run doctor, then send a real hello to the provider")
    parser.add_argument("--mode", choices=["default", "auto", "safe", "plan", "ask"],
                        help="Permission mode for tool execution")
    parser.add_argument("--profile", choices=["fast", "balanced", "deep"],
                        help="Runtime response profile")
    parser.add_argument("--run-due-jobs", action="store_true",
                        help="Run all due automation jobs once and exit")
    parser.add_argument("--scheduler", action="store_true",
                        help="Run the local scheduler loop in the foreground")
    parser.add_argument("--scheduler-poll", type=float, default=30.0,
                        help="Scheduler polling interval in seconds")
    parser.add_argument("--serve-webhooks", action="store_true",
                        help="Serve local webhook routes in the foreground")
    parser.add_argument("--webhook-host", default="127.0.0.1",
                        help="Webhook host (default 127.0.0.1)")
    parser.add_argument("--webhook-port", type=int, default=8765,
                        help="Webhook port (default 8765)")
    parser.add_argument("--bench", action="store_true",
                        help="Run the local benchmark suite and exit")
    parser.add_argument("--bench-dry-run", action="store_true",
                        help="Validate benchmark tasks without LLM calls")
    parser.add_argument("--bench-out", default="bench_results.json",
                        help="Where to write benchmark results")
    parser.add_argument("-p", "--prompt", help="Run one prompt non-interactively and exit")
    parser.add_argument("--persona", help="Activate a saved persona by name")
    parser.add_argument("--distill", metavar="SENTENCE",
                        help="Distill a new persona from a sentence, activate, enter REPL")
    parser.add_argument("--resume", nargs="?", const=LAST_SESSION_NAME, metavar="NAME",
                        help="Resume a saved session (default: 'last')")
    parser.add_argument("--fresh", action="store_true",
                        help="Skip auto-resume of 'last'; start from a clean slate")
    args = parser.parse_args()

    if args.setup:
        _run_setup(args.setup, api_key=args.api_key or "", model=args.setup_model or "")
        return

    try:
        cfg = load_config(provider_override=args.provider)
    except Exception as e:
        ui.error(str(e))
        ui.info("For the simplest free path, run: xirang --setup openrouter")
        sys.exit(1)
    if args.model:
        cfg.model = args.model
    if args.mode:
        cfg.mode = args.mode
    if args.profile:
        cfg.response_profile = args.profile

    if args.doctor_live:
        sys.exit(0 if _run_doctor_live(cfg) else 1)

    if args.doctor:
        _run_doctor(cfg)
        return

    if args.run_due_jobs:
        rows = auto.run_due_jobs(cfg)
        ui.markdown("\n".join(["**Due job results**"] + [f"- `{row['job']}` · success={row['success']}" for row in rows]) if rows else "No due jobs.")
        return

    if args.scheduler:
        ui.status(f"running scheduler loop (poll={args.scheduler_poll}s)")
        auto.scheduler_loop(cfg, poll_seconds=args.scheduler_poll)
        return

    if args.serve_webhooks:
        ui.status(f"serving webhooks on http://{args.webhook_host}:{args.webhook_port}")
        auto.serve_webhooks(cfg, host=args.webhook_host, port=args.webhook_port)
        return

    if args.bench or args.bench_dry_run:
        report = bench.run_benchmark(
            cfg,
            dry_run=args.bench_dry_run,
            out_path=Path(args.bench_out).expanduser(),
        )
        ui.markdown(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if args.bench_dry_run or report.get("failed", 0) == 0 else 1)

    # --- single-shot ---
    if args.prompt:
        agent = _build_agent(cfg, persona_name=args.persona, resume=args.resume)
        if args.profile:
            agent.set_response_profile(args.profile)
        turn = agent.turn(args.prompt)
        if args.resume or agent.turn_count > 0:
            try:
                sess.save(cfg.home, args.resume or agent.current_session_name, agent)
            except Exception:
                pass
        sys.exit(0 if turn.success else 1)

    # --- distill + REPL ---
    if args.distill:
        agent = _build_agent(cfg)
        if args.profile:
            agent.set_response_profile(args.profile)
        ui.show_banner(
            cfg.model,
            cfg.provider,
            brand=cfg.brand,
            mode=cfg.mode,
            session=agent.current_session_name,
            profile=cfg.response_profile,
        )
        ui.status(f"distilling persona from: {args.distill}")
        try:
            p = per.distill(agent.llm, args.distill)
        except Exception as e:
            ui.error(f"distillation failed: {e}")
            sys.exit(1)
        per.save(cfg.personas_dir, p)
        agent.persona = p
        agent.persona_mode = "default"
        ui.success(f"persona '{p.name}' active")
        ui.markdown(f"**Essence:** {p.essence}")
        _repl(agent)
        return

    # --- default REPL (with implicit resume of 'last' if it exists) ---
    resume_target = args.resume
    if resume_target is None and not args.fresh:
        # Auto-pick up yesterday's 'last' if present, silently skip if not
        if (cfg.home / "sessions" / f"{LAST_SESSION_NAME}.json").exists():
            resume_target = LAST_SESSION_NAME
    agent = _build_agent(cfg, persona_name=args.persona, resume=resume_target)
    if args.profile:
        agent.set_response_profile(args.profile)
    banner_persona = agent.persona.name if agent.persona else None
    ui.show_banner(
        agent.cfg.model,
        agent.cfg.provider,
        persona=banner_persona,
        brand=agent.cfg.brand,
        mode=agent.cfg.mode,
        session=agent.current_session_name,
        profile=agent.cfg.response_profile,
        persona_mode=agent.persona_mode,
    )
    _repl(agent)


if __name__ == "__main__":
    main()
