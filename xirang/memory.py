"""Layered memory — OpenMythos-inspired staged context loading.

OpenMythos uses a staged architecture:
- Prelude: always-on base context
- Recurrent: compact state reused across steps
- Coda: final refinement layers

This module adapts that idea to an agent memory system:
- `prelude/`  : stable user/project facts that should usually stay in scope
- `recurrent/`: rolling session summaries and recent task state
- `coda/`     : compact task outcomes, lessons, and conclusions
- `archive/`  : raw or longer reference memories, recalled only when relevant

Everything is file-based and local. Prompt injection is retrieval-driven and
bounded by a byte budget, so the memory inventory can grow while prompt load
stays targeted.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from xirang import recipe


INDEX_NAME = "MEMORY.md"
INDEX_PREVIEW_LIMIT = 400
DEFAULT_CONTEXT_BUDGET_BYTES = 2 * 1024 * 1024
LAYERS = ("prelude", "recurrent", "coda", "archive")
ALWAYS_ON_LAYERS = ("prelude",)
LAYER_SELECTION_CAPS = {"prelude": 6, "recurrent": 4, "coda": 4, "archive": 3}
MIXED_RECALL_ORDER = ("recurrent", "coda", "archive")
PERSISTENT_RULE_TYPES = {"rule", "preference", "instruction"}
CONTINUITY_RE = re.compile(
    r"(上次|昨天|前天|之前|刚才|继续|接着|还记得|想起来|last|yesterday|previous|continue|recap)",
    re.IGNORECASE,
)
DAILY_JOURNAL_MAX_ENTRIES = 120


@dataclass
class MemoryFile:
    name: str
    description: str
    type: str
    body: str
    path: Path
    layer: str = "archive"
    tags: list[str] = field(default_factory=list)
    source: str = ""
    updated_at: float = 0.0


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "_", text)[:60] or "memory"


def _ensure_layout(memory_dir: Path) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    for layer in LAYERS:
        (memory_dir / layer).mkdir(parents=True, exist_ok=True)


def _normalize_layer(layer: str | None, mem_type: str = "") -> str:
    if layer in LAYERS:
        return str(layer)
    if mem_type in {"user", "feedback", "project", "rule", "preference", "instruction"}:
        return "prelude"
    if mem_type in {"session", "summary", "state"}:
        return "recurrent"
    if mem_type in {"lesson", "outcome"}:
        return "coda"
    return "archive"


def _index_path(memory_dir: Path) -> Path:
    _ensure_layout(memory_dir)
    return memory_dir / INDEX_NAME


def _layer_path(memory_dir: Path, layer: str, slug: str) -> Path:
    _ensure_layout(memory_dir)
    return memory_dir / layer / f"{slug}.md"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n([\s\S]*?)\n---\n?", text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, text[match.end():].strip()


def _record_from_path(path: Path) -> MemoryFile | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    meta, body = _parse_frontmatter(text)
    tags_raw = meta.get("tags_json", "[]")
    try:
        tags = json.loads(tags_raw)
    except Exception:
        tags = []
    return MemoryFile(
        name=meta.get("name", path.stem),
        description=meta.get("description", ""),
        type=meta.get("type", ""),
        body=body,
        path=path,
        layer=meta.get("layer", path.parent.name),
        tags=tags if isinstance(tags, list) else [],
        source=meta.get("source", ""),
        updated_at=float(meta.get("updated_at", path.stat().st_mtime)),
    )


def _all_records(memory_dir: Path) -> list[MemoryFile]:
    _ensure_layout(memory_dir)
    records: list[MemoryFile] = []
    for layer in LAYERS:
        for fp in (memory_dir / layer).glob("*.md"):
            record = _record_from_path(fp)
            if record:
                records.append(record)
    return sorted(records, key=lambda item: (-item.updated_at, item.name))


def _upsert_index(memory_dir: Path) -> None:
    lines = [
        "# Xirang Layered Memory Index",
        "",
        "OpenMythos-inspired layout: prelude → recurrent → coda → archive",
        "",
    ]
    grouped: dict[str, list[MemoryFile]] = {layer: [] for layer in LAYERS}
    for record in _all_records(memory_dir):
        grouped[record.layer].append(record)
    for layer in LAYERS:
        items = grouped[layer]
        if not items:
            continue
        lines.append(f"## {layer}")
        for record in items[:120]:
            rel = record.path.relative_to(memory_dir)
            lines.append(
                f"- [{record.name}]({rel.as_posix()}) — {record.description or record.type or record.layer}"
            )
        lines.append("")
    _index_path(memory_dir).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def load_index(memory_dir: Path) -> str:
    p = _index_path(memory_dir)
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8").splitlines()[:INDEX_PREVIEW_LIMIT]
    return "\n".join(lines)


def save_memory(
    memory_dir: Path,
    name: str,
    description: str,
    mem_type: str,
    body: str,
    *,
    layer: str | None = None,
    tags: list[str] | None = None,
    source: str = "",
) -> Path:
    _ensure_layout(memory_dir)
    slug = _slugify(name)
    resolved_layer = _normalize_layer(layer, mem_type)
    fp = _layer_path(memory_dir, resolved_layer, slug)
    fp.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                f"type: {mem_type}",
                f"layer: {resolved_layer}",
                f"source: {source}",
                f"updated_at: {time.time()}",
                f"tags_json: {json.dumps(tags or [], ensure_ascii=False)}",
                "---",
                "",
                body.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    _upsert_index(memory_dir)
    return fp


def forget(memory_dir: Path, name: str) -> bool:
    _ensure_layout(memory_dir)
    slug = _slugify(name)
    removed = False
    for layer in LAYERS:
        fp = _layer_path(memory_dir, layer, slug)
        if fp.exists():
            fp.unlink()
            removed = True
    if removed:
        _upsert_index(memory_dir)
    return removed


def _is_persistent_rule(record: MemoryFile) -> bool:
    return record.layer == "prelude" and (
        record.type in PERSISTENT_RULE_TYPES or "sticky" in record.tags or "rule" in record.tags
    )


def save_rule(
    memory_dir: Path,
    name: str,
    body: str,
    *,
    description: str = "",
    source: str = "user_rule",
) -> Path:
    text = (body or "").strip()
    desc = (description or text[:100]).strip()
    return save_memory(
        memory_dir,
        name=name.strip(),
        description=desc,
        mem_type="rule",
        body=text,
        layer="prelude",
        tags=["sticky", "rule"],
        source=source,
    )


def _token_set(text: str) -> set[str]:
    return set(recipe.fingerprint(text).split())


def _score_record(record: MemoryFile, query: str) -> float:
    query_tokens = _token_set(query)
    continuity = _is_continuity_query(query)
    if not query_tokens and not continuity:
        return 0.0
    haystack = " ".join(
        [
            record.name,
            record.description,
            record.type,
            record.layer,
            " ".join(record.tags),
            record.body[:3000],
        ]
    )
    record_tokens = _token_set(haystack)
    if not record_tokens:
        return 0.0
    overlap = len(query_tokens & record_tokens)
    if overlap == 0 and not continuity:
        return 0.0
    age_hours = max((time.time() - record.updated_at) / 3600.0, 0.0)
    freshness_bonus = 1.0 / (1.0 + age_hours / 72.0)
    layer_bonus = {"prelude": 0.4, "recurrent": 0.3, "coda": 0.2, "archive": 0.1}.get(record.layer, 0)
    continuity_bonus = 8.0 if continuity and record.layer in {"recurrent", "coda"} else 0.0
    return overlap * 10 + layer_bonus + freshness_bonus + continuity_bonus


def _score_prelude_record(record: MemoryFile, query: str) -> float:
    query_tokens = _token_set(query)
    overlap = 0
    if query_tokens:
        haystack = " ".join([record.name, record.description, record.body[:1500]])
        overlap = len(query_tokens & _token_set(haystack))
    age_hours = max((time.time() - record.updated_at) / 3600.0, 0.0)
    freshness_bonus = 1.0 / (1.0 + age_hours / 168.0)
    sticky_bonus = 12.0 if _is_persistent_rule(record) else 0.0
    return 5.0 + overlap * 8 + freshness_bonus + sticky_bonus


def _body_excerpt(record: MemoryFile, query: str, max_chars: int = 1600) -> str:
    body = record.body.strip()
    if not body:
        return record.description
    query_tokens = list(_token_set(query))
    lower = body.lower()
    for token in query_tokens:
        idx = lower.find(token.lower())
        if idx >= 0:
            start = max(idx - 220, 0)
            end = min(idx + 900, len(body))
            excerpt = body[start:end].strip()
            return excerpt[:max_chars]
    return body[:max_chars]


def _is_continuity_query(query: str) -> bool:
    return bool(CONTINUITY_RE.search(query or ""))


def render_for_system_prompt(
    memory_dir: Path,
    query: str = "",
    budget_bytes: int = DEFAULT_CONTEXT_BUDGET_BYTES,
) -> str:
    records = _all_records(memory_dir)
    if not records:
        return ""

    selected: list[tuple[str, MemoryFile, str]] = []
    used_bytes = 0

    def try_add(section: str, record: MemoryFile, content: str) -> None:
        nonlocal used_bytes
        payload = (
            f"## {section}\n"
            f"- name: {record.name}\n"
            f"- type: {record.type}\n"
            f"- layer: {record.layer}\n"
            f"- summary: {record.description}\n"
            f"- content: {content}\n"
        )
        size = len(payload.encode("utf-8"))
        if used_bytes + size > budget_bytes:
            return
        selected.append((section, record, content))
        used_bytes += size

    persistent_rules = sorted(
        [record for record in records if _is_persistent_rule(record)],
        key=lambda record: (-record.updated_at, record.name),
    )[:12]
    for record in persistent_rules:
        try_add("Persistent User Rules", record, _body_excerpt(record, query or record.name, max_chars=1200))

    preludes = sorted(
        [record for record in records if record.layer in ALWAYS_ON_LAYERS and not _is_persistent_rule(record)],
        key=lambda record: _score_prelude_record(record, query),
        reverse=True,
    )[:LAYER_SELECTION_CAPS["prelude"]]
    for record in preludes:
        try_add("Prelude Memory", record, _body_excerpt(record, query or record.name, max_chars=2200))

    for _, record in _mixed_ranked_records(records, query):
        section = {
            "recurrent": "Recurrent Memory",
            "coda": "Coda Memory",
            "archive": "Archive Recall",
        }.get(record.layer, "Memory")
        try_add(section, record, _body_excerpt(record, query))

    if not selected:
        return ""

    lines = [
        "\n# Layered memory context",
        f"- loaded_bytes: {used_bytes}",
        f"- budget_bytes: {budget_bytes}",
        "- Treat Persistent User Rules as active defaults across sessions unless the user changes or removes them.",
        "- Apply prelude memory as stable context.",
        "- Apply recurrent/coda/archive only if they match the current request.",
        "",
    ]
    for section, record, content in selected:
        lines.extend(
            [
                f"## {section}",
                f"- name: {record.name}",
                f"- type: {record.type}",
                f"- layer: {record.layer}",
                f"- summary: {record.description}",
                f"- content: {content}",
                "",
            ]
        )
    lines.append(
        "If a recalled memory conflicts with the current repository state or user instruction, trust the live evidence."
    )
    return "\n".join(lines)


def search(memory_dir: Path, query: str, limit: int = 8) -> list[tuple[float, MemoryFile]]:
    query = (query or "").strip()
    if not query:
        return []
    records = _all_records(memory_dir)
    preludes = sorted(
        [
            (_score_prelude_record(record, query), record)
            for record in records
            if record.layer in ALWAYS_ON_LAYERS
        ],
        key=lambda item: (-item[0], -item[1].updated_at, item[1].name),
    )[:2]
    mixed = _mixed_ranked_records(records, query)
    ranked = preludes + mixed
    return ranked[:max(limit, 1)]


def recent(memory_dir: Path, limit: int = 8, layers: tuple[str, ...] | None = None) -> list[MemoryFile]:
    records = _all_records(memory_dir)
    if layers:
        records = [record for record in records if record.layer in layers]
    return records[:max(limit, 1)]


def persistent_rules(memory_dir: Path, limit: int = 12) -> list[MemoryFile]:
    records = [record for record in _all_records(memory_dir) if _is_persistent_rule(record)]
    return records[:max(limit, 1)]


def stats(memory_dir: Path) -> dict[str, int]:
    counts = {layer: 0 for layer in LAYERS}
    for record in _all_records(memory_dir):
        counts[record.layer] = counts.get(record.layer, 0) + 1
    counts["total"] = sum(counts[layer] for layer in LAYERS)
    return counts


def _mixed_ranked_records(records: list[MemoryFile], query: str) -> list[tuple[float, MemoryFile]]:
    per_layer: dict[str, list[tuple[float, MemoryFile]]] = {layer: [] for layer in MIXED_RECALL_ORDER}
    for record in records:
        if record.layer in ALWAYS_ON_LAYERS:
            continue
        score = _score_record(record, query)
        if score <= 0:
            continue
        per_layer.setdefault(record.layer, []).append((score, record))
    for layer, items in per_layer.items():
        items.sort(key=lambda item: (-item[0], -item[1].updated_at, item[1].name))
        per_layer[layer] = items[:LAYER_SELECTION_CAPS.get(layer, 3)]

    mixed: list[tuple[float, MemoryFile]] = []
    seen_paths: set[Path] = set()
    while True:
        advanced = False
        for layer in MIXED_RECALL_ORDER:
            items = per_layer.get(layer, [])
            while items:
                score, record = items.pop(0)
                if record.path in seen_paths:
                    continue
                seen_paths.add(record.path)
                mixed.append((score, record))
                advanced = True
                break
        if not advanced:
            break
    return mixed


def capture_session(
    memory_dir: Path,
    session_name: str,
    messages: list[dict],
    turn_count: int,
) -> None:
    """Compress a session into recurrent + coda memory layers.

    This is intentionally deterministic and local: it avoids extra LLM calls.
    """
    _ensure_layout(memory_dir)
    user_lines: list[str] = []
    assistant_lines: list[str] = []
    for item in messages:
        role = item.get("role")
        content = item.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            text = "\n".join(parts).strip()
        else:
            text = str(content).strip()
        if not text:
            continue
        if role == "user":
            user_lines.append(text)
        elif role == "assistant":
            assistant_lines.append(text)

    recent_user = user_lines[-8:]
    recent_assistant = assistant_lines[-4:]
    fingerprint = recipe.fingerprint(" ".join(recent_user[-4:]))
    summary_body = "\n".join(
        [
            f"session: {session_name}",
            f"turns: {turn_count}",
            f"fingerprint: {fingerprint}",
            "",
            "recent_user_requests:",
            *(f"- {line[:300]}" for line in recent_user),
            "",
            "recent_assistant_outcomes:",
            *(f"- {line[:300]}" for line in recent_assistant),
        ]
    )
    save_memory(
        memory_dir,
        name=f"session_{session_name}",
        description=f"Rolling summary for session '{session_name}' with {turn_count} turns",
        mem_type="session",
        body=summary_body,
        layer="recurrent",
        tags=fingerprint.split()[:12],
        source=f"session:{session_name}",
    )

    if recent_assistant:
        coda_body = "\n".join(recent_assistant[-3:])
        save_memory(
            memory_dir,
            name=f"session_{session_name}_outcome",
            description=f"Recent outcomes and conclusions from session '{session_name}'",
            mem_type="outcome",
            body=coda_body,
            layer="coda",
            tags=fingerprint.split()[:12],
            source=f"session:{session_name}",
        )


def capture_turn(
    memory_dir: Path,
    session_name: str,
    user_input: str,
    assistant_output: str,
    turn_count: int,
    *,
    persona_slug: str = "",
) -> None:
    """Persist a single turn into a daily journal for multi-day continuity."""
    user_input = (user_input or "").strip()
    assistant_output = (assistant_output or "").strip()
    if not user_input and not assistant_output:
        return
    _ensure_layout(memory_dir)
    day = datetime.fromtimestamp(time.time()).strftime("%Y_%m_%d")
    name = f"daily_{day}"
    slug = _slugify(name)
    fp = _layer_path(memory_dir, "recurrent", slug)
    entries: list[dict] = []
    if fp.exists():
        record = _record_from_path(fp)
        if record:
            match = re.search(r"```json\n([\s\S]*?)\n```", record.body)
            if match:
                try:
                    loaded = json.loads(match.group(1))
                    if isinstance(loaded, list):
                        entries = loaded
                except Exception:
                    entries = []
    entries.append(
        {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "session": session_name,
            "turn": turn_count,
            "persona": persona_slug,
            "user": user_input[:500],
            "assistant": assistant_output[:500],
            "fingerprint": recipe.fingerprint(user_input),
        }
    )
    entries = entries[-DAILY_JOURNAL_MAX_ENTRIES:]
    recent_lines = []
    for entry in entries[-12:]:
        who = f" persona={entry['persona']}" if entry.get("persona") else ""
        recent_lines.append(
            f"- {entry['ts']} [{entry['session']}#{entry['turn']}{who}] "
            f"user: {entry['user'][:160]} | assistant: {entry['assistant'][:180]}"
        )
    body = "\n".join(
        [
            f"Daily conversation journal for {day.replace('_', '-')}.",
            "Use this when the user asks to continue, recall yesterday, or remember the previous discussion.",
            "",
            "recent_entries:",
            *recent_lines,
            "",
            "structured_entries:",
            "```json",
            json.dumps(entries, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    save_memory(
        memory_dir,
        name=name,
        description=f"Daily conversation journal for {day.replace('_', '-')}",
        mem_type="session",
        body=body,
        layer="recurrent",
        tags=["daily", "conversation", "continuity", *recipe.fingerprint(user_input).split()[:8]],
        source=f"session:{session_name}",
    )
