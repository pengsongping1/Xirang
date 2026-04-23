"""Explicit human + agent desktop co-pilot sessions.

The co-pilot layer is intentionally a visible session wrapper around the
`desktop` tool. It records opt-in state, can run bounded observations, and can
turn a user invitation into an agent prompt. It does not install hooks,
keyloggers, or background listeners.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from xirang import desktop


STATE_NAME = "session.json"


def _dir(home: Path) -> Path:
    path = home / "copilot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(home: Path) -> Path:
    return _dir(home) / STATE_NAME


def _load_state(home: Path) -> dict[str, Any]:
    fp = _state_path(home)
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(home: Path, state: dict[str, Any]) -> Path:
    fp = _state_path(home)
    fp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return fp


def _desktop_status() -> dict[str, Any]:
    try:
        data = json.loads(desktop.desktop(action="status"))
        return data if isinstance(data, dict) else {"raw": data}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def start(home: Path, task: str = "") -> dict[str, Any]:
    """Start an explicit local co-pilot session for this process."""
    now = time.time()
    os.environ[desktop.ENABLE_ENV] = "1"
    previous = _load_state(home)
    state = {
        "active": True,
        "task": task.strip(),
        "started_at": previous.get("started_at") or now,
        "updated_at": now,
        "env": desktop.ENABLE_ENV,
        "safety": {
            "background_keylogger": False,
            "hidden_monitoring": False,
            "watch_is_bounded": True,
            "manual_upload_only": True,
        },
    }
    _save_state(home, state)
    return {**state, "desktop": _desktop_status()}


def stop(home: Path) -> dict[str, Any]:
    """Stop the visible co-pilot session for this process."""
    state = _load_state(home)
    state.update({"active": False, "stopped_at": time.time(), "updated_at": time.time()})
    _save_state(home, state)
    os.environ.pop(desktop.ENABLE_ENV, None)
    return {**state, "desktop": _desktop_status()}


def status(home: Path) -> dict[str, Any]:
    """Return co-pilot state plus desktop tool availability."""
    state = _load_state(home)
    return {
        "active": bool(state.get("active")),
        "task": state.get("task", ""),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "state_path": str(_state_path(home)),
        "desktop": _desktop_status(),
    }


def screenshot(home: Path, path: str = "") -> str:
    """Take one explicit screenshot through the desktop tool."""
    out = Path(path).expanduser() if path else _dir(home) / f"screenshot-{int(time.time())}.png"
    return desktop.desktop(action="screenshot", path=str(out))


def observe(home: Path, seconds: float = 3.0) -> str:
    """Run a short, bounded screenshot watch session."""
    out_dir = _dir(home) / f"watch-{int(time.time())}"
    return desktop.desktop(action="watch", duration=seconds, interval=1.0, path=str(out_dir))


def invitation_prompt(task: str, observation: str = "") -> str:
    """Build the user message used when Xirang is invited into a live task."""
    lines = [
        "用户显式邀请你加入一个本机桌面共操任务。",
        "",
        "协作规则：",
        "- 先理解用户当前目标，再决定是否需要截图、鼠标或键盘工具。",
        "- 用户也会继续操作；你不要抢控制权，只做小步、可逆、可解释的协作。",
        "- 如果要点击、输入、热键或拖拽，优先说明你要做的一小步。",
        "- 禁止后台监听、禁止偷录输入、禁止自动上传本地进化数据。",
        "",
        f"用户邀请：{task.strip() or '观察当前状态，等待我继续指令。'}",
    ]
    if observation.strip():
        lines.extend(["", "最近一次显式观察结果：", observation.strip()])
    return "\n".join(lines)
