"""Optional desktop co-pilot tool.

This tool is intentionally opt-in. It can move/click/type only when
`XIRANG_DESKTOP_ENABLE=1` is set. It never installs a background keylogger and
does not continuously listen to user input. The `watch` action is bounded,
explicit, and screenshot-based.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from xirang.tools import tool


ENABLE_ENV = "XIRANG_DESKTOP_ENABLE"
MAX_WATCH_SECONDS = 15
MAX_WATCH_FRAMES = 20


def _enabled() -> bool:
    return os.getenv(ENABLE_ENV, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _home() -> Path:
    return Path(os.getenv("XIRANG_HOME") or (Path.home() / ".xirang")).expanduser()


def _pyautogui():
    try:
        import pyautogui
    except Exception as e:
        raise RuntimeError(
            "pyautogui is not available. Install desktop control extras with: "
            "pip install pyautogui pillow"
        ) from e
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


def _availability() -> dict[str, Any]:
    info: dict[str, Any] = {"enabled": _enabled(), "env": ENABLE_ENV}
    try:
        pg = _pyautogui()
        pos = pg.position()
        size = pg.size()
        info.update(
            {
                "pyautogui_available": True,
                "cursor": [int(pos.x), int(pos.y)],
                "screen_size": [int(size.width), int(size.height)],
            }
        )
    except Exception as e:
        info.update({"pyautogui_available": False, "error": f"{type(e).__name__}: {e}"})
    return info


def _guard(action: str) -> str | None:
    if action == "status":
        return None
    if not _enabled():
        return (
            "Desktop control is disabled. Set XIRANG_DESKTOP_ENABLE=1 to allow "
            "explicit local mouse/keyboard/screenshot actions. This is disabled "
            "by default for safety."
        )
    return None


def _maybe_move(pg, x: int | None, y: int | None, duration: float = 0.0) -> None:
    if x is not None and y is not None:
        pg.moveTo(int(x), int(y), duration=max(float(duration), 0.0))


def _json(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="desktop",
    description=(
        "Opt-in local desktop co-pilot tool for mouse/keyboard/screenshot actions. "
        "Requires XIRANG_DESKTOP_ENABLE=1 and pyautogui. Use when the user wants "
        "the agent to collaborate in normal desktop apps instead of only editing "
        "files or running CLI commands. Actions: status, screenshot, move, click, "
        "double_click, drag, scroll, type_text, hotkey, press, watch. Never use "
        "for hidden monitoring; watch is explicit and bounded."
    ),
    schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status",
                    "screenshot",
                    "move",
                    "click",
                    "double_click",
                    "drag",
                    "scroll",
                    "type_text",
                    "hotkey",
                    "press",
                    "watch",
                ],
            },
            "x": {"type": "integer", "description": "Screen x coordinate"},
            "y": {"type": "integer", "description": "Screen y coordinate"},
            "button": {"type": "string", "enum": ["left", "middle", "right"]},
            "clicks": {"type": "integer", "description": "Click count"},
            "amount": {"type": "integer", "description": "Scroll amount; positive up, negative down"},
            "text": {"type": "string", "description": "Text for type_text"},
            "key": {"type": "string", "description": "Single key for press"},
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key sequence for hotkey, e.g. ['ctrl','s']",
            },
            "duration": {"type": "number", "description": "Move/drag/watch duration seconds"},
            "interval": {"type": "number", "description": "Typing or watch interval seconds"},
            "path": {"type": "string", "description": "Screenshot path or watch output directory"},
        },
        "required": ["action"],
    },
)
def desktop(
    action: str,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
    amount: int = 0,
    text: str = "",
    key: str = "",
    keys: list[str] | None = None,
    duration: float = 0.0,
    interval: float = 0.0,
    path: str = "",
) -> str:
    action = (action or "").strip()
    if action == "status":
        return _json(_availability())

    blocked = _guard(action)
    if blocked:
        return blocked

    try:
        pg = _pyautogui()

        if action == "screenshot":
            out = Path(path).expanduser() if path else _home() / "desktop" / f"screenshot-{int(time.time())}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            image = pg.screenshot()
            image.save(out)
            return _json({"action": action, "path": str(out), "size": [image.width, image.height]})

        if action == "move":
            if x is None or y is None:
                return "Error: x and y are required for move"
            pg.moveTo(int(x), int(y), duration=max(float(duration), 0.0))
            return _json({"action": action, "cursor": [int(x), int(y)]})

        if action == "click":
            _maybe_move(pg, x, y, duration=duration)
            pg.click(button=button or "left", clicks=max(int(clicks or 1), 1), interval=max(float(interval), 0.0))
            pos = pg.position()
            return _json({"action": action, "cursor": [int(pos.x), int(pos.y)], "button": button, "clicks": clicks})

        if action == "double_click":
            _maybe_move(pg, x, y, duration=duration)
            pg.doubleClick(button=button or "left")
            pos = pg.position()
            return _json({"action": action, "cursor": [int(pos.x), int(pos.y)], "button": button})

        if action == "drag":
            if x is None or y is None:
                return "Error: x and y are required for drag"
            pg.dragTo(int(x), int(y), duration=max(float(duration), 0.1), button=button or "left")
            return _json({"action": action, "cursor": [int(x), int(y)], "button": button})

        if action == "scroll":
            _maybe_move(pg, x, y, duration=0)
            pg.scroll(int(amount))
            pos = pg.position()
            return _json({"action": action, "cursor": [int(pos.x), int(pos.y)], "amount": int(amount)})

        if action == "type_text":
            if not text:
                return "Error: text is required for type_text"
            pg.write(text, interval=max(float(interval), 0.0))
            return _json({"action": action, "typed_chars": len(text)})

        if action == "hotkey":
            keys = [str(k).strip() for k in (keys or []) if str(k).strip()]
            if not keys:
                return "Error: keys are required for hotkey"
            pg.hotkey(*keys)
            return _json({"action": action, "keys": keys})

        if action == "press":
            if not key:
                return "Error: key is required for press"
            pg.press(key, presses=max(int(clicks or 1), 1), interval=max(float(interval), 0.0))
            return _json({"action": action, "key": key, "presses": max(int(clicks or 1), 1)})

        if action == "watch":
            seconds = min(max(float(duration or 3.0), 0.5), MAX_WATCH_SECONDS)
            step = min(max(float(interval or 1.0), 0.25), 5.0)
            out_dir = Path(path).expanduser() if path else _home() / "desktop" / f"watch-{int(time.time())}"
            out_dir.mkdir(parents=True, exist_ok=True)
            frames: list[dict[str, Any]] = []
            started = time.time()
            index = 0
            while time.time() - started <= seconds and index < MAX_WATCH_FRAMES:
                pos = pg.position()
                image = pg.screenshot()
                fp = out_dir / f"frame-{index:03d}.png"
                image.save(fp)
                frames.append(
                    {
                        "t": round(time.time() - started, 2),
                        "cursor": [int(pos.x), int(pos.y)],
                        "path": str(fp),
                    }
                )
                index += 1
                time.sleep(step)
            return _json({"action": action, "duration": round(time.time() - started, 2), "frames": frames})

        return f"Error: unknown desktop action: {action}"
    except Exception as e:
        return f"Desktop error: {type(e).__name__}: {e}"
