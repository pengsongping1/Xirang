"""Persistent sessions — save/load conversations across restarts.

Storage: ~/.xirang/sessions/<name>.json
Format: {messages, total_usage, persona_slug, persona_mode, started_at, last_saved_at}

Anthropic content blocks contain non-serializable SDK objects; we serialize
them to plain dicts so replay works across provider switches too.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xirang import memory as mem


def _block_to_dict(b: Any) -> dict:
    """Coerce an anthropic content block (or already-dict) to a plain dict."""
    if isinstance(b, dict):
        return b
    t = getattr(b, "type", None)
    if t == "text":
        return {"type": "text", "text": getattr(b, "text", "")}
    if t == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    if t == "tool_result":
        return {"type": "tool_result", "tool_use_id": getattr(b, "tool_use_id", ""),
                "content": getattr(b, "content", "")}
    if t == "thinking":
        return {"type": "thinking", "thinking": getattr(b, "thinking", ""),
                "signature": getattr(b, "signature", "")}
    # Fallback — best-effort
    return {"type": t or "unknown", "raw": str(b)}


def _serialize_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m["role"]
        content = m.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        elif isinstance(content, list):
            out.append({"role": role, "content": [_block_to_dict(b) for b in content]})
        else:
            out.append({"role": role, "content": str(content)})
    return out


@dataclass
class SessionBlob:
    name: str
    messages: list[dict] = field(default_factory=list)
    total_usage: dict = field(default_factory=dict)
    persona_slug: str | None = None
    persona_mode: str | None = None
    provider: str = ""
    model: str = ""
    tool_mode: str = ""
    response_profile: str = ""
    started_at: float = field(default_factory=time.time)
    last_saved_at: float = field(default_factory=time.time)
    turn_count: int = 0


def _sessions_dir(home: Path) -> Path:
    d = home / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(home: Path, name: str, agent) -> Path:
    """Save an Agent's state to sessions/<name>.json."""
    blob = SessionBlob(
        name=name,
        messages=_serialize_messages(agent.messages),
        total_usage=dict(agent.total_usage),
        persona_slug=(agent.persona.slug if agent.persona else None),
        persona_mode=getattr(agent, "persona_mode", None),
        provider=agent.cfg.provider,
        model=agent.cfg.model,
        tool_mode=getattr(agent.cfg, "mode", ""),
        response_profile=getattr(agent.cfg, "response_profile", ""),
        started_at=getattr(agent, "started_at", time.time()),
        last_saved_at=time.time(),
        turn_count=getattr(agent, "turn_count", 0),
    )
    fp = _sessions_dir(home) / f"{name}.json"
    fp.write_text(
        json.dumps(blob.__dict__, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    try:
        mem.capture_session(agent.cfg.memory_dir, name, agent.messages, blob.turn_count)
    except Exception:
        pass
    return fp


def load(home: Path, name: str) -> SessionBlob | None:
    fp = _sessions_dir(home) / f"{name}.json"
    if not fp.exists():
        return None
    data = json.loads(fp.read_text(encoding="utf-8"))
    return SessionBlob(**data)


def list_sessions(home: Path) -> list[dict]:
    out = []
    for fp in sorted(_sessions_dir(home).glob("*.json"), key=lambda p: -p.stat().st_mtime):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
            out.append({
                "name": d.get("name", fp.stem),
                "turns": d.get("turn_count", 0),
                "saved": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("last_saved_at", 0))),
                "model": d.get("model", "?"),
                "persona": d.get("persona_slug"),
                "mode": d.get("persona_mode"),
            })
        except Exception:
            continue
    return out


def delete(home: Path, name: str) -> bool:
    fp = _sessions_dir(home) / f"{name}.json"
    if fp.exists():
        fp.unlink()
        return True
    return False


def apply_to_agent(blob: SessionBlob, agent) -> None:
    """Restore session state onto a fresh Agent."""
    agent.messages = list(blob.messages)
    agent.total_usage = dict(blob.total_usage) or {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
    agent.started_at = blob.started_at
    agent.last_saved_at = blob.last_saved_at
    agent.turn_count = blob.turn_count
    if blob.provider and hasattr(agent, "switch_provider"):
        agent.switch_provider(blob.provider)
    elif blob.provider:
        agent.cfg.provider = blob.provider
    if blob.model:
        agent.cfg.model = blob.model
    if blob.tool_mode:
        agent.cfg.mode = blob.tool_mode
    if blob.response_profile:
        if hasattr(agent, "set_response_profile"):
            agent.set_response_profile(blob.response_profile)
        else:
            agent.cfg.response_profile = blob.response_profile
    if hasattr(agent, "reload_runtime_client"):
        agent.reload_runtime_client()
    if blob.persona_slug:
        from xirang import persona as per
        p = per.load(agent.cfg.personas_dir, blob.persona_slug)
        if p:
            agent.persona = p
    agent.persona_mode = blob.persona_mode
