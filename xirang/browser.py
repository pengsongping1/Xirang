"""Persistent browser — Playwright sync, one context per xirang session.

Single `browser` tool with sub-actions. Page and context persist across
tool calls, so you can navigate → click → extract → screenshot without
re-loading pages. Lazy-init: no Playwright launch until first use.

Requires: pip install playwright && playwright install chromium

The tool is OPTIONAL — agent works fine without playwright installed.
Registration happens via `maybe_register()` at import time.
"""
from __future__ import annotations

import atexit
from pathlib import Path
from typing import Any

from xirang.tools import tool


class _BrowserState:
    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self.headless: bool = True

    def ensure(self) -> Any:
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "playwright not installed. run: pip install playwright && "
                "playwright install chromium"
            ) from e
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Xirang-Agent) AppleWebKit/537.36",
        )
        self._page = self._context.new_page()
        return self._page

    def close(self) -> None:
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._page = self._context = self._browser = self._pw = None


_state = _BrowserState()
atexit.register(_state.close)


@tool(
    name="browser",
    description=(
        "Persistent web browser (Playwright Chromium). Useful for JS-rendered "
        "pages, multi-step interactions, or anything curl can't handle. "
        "Page state persists across calls in this session. "
        "Actions: navigate / extract_text / extract_html / click / fill / "
        "screenshot / close. For simple static fetches, prefer `bash curl`."
    ),
    schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["navigate", "extract_text", "extract_html",
                         "click", "fill", "screenshot", "close"],
            },
            "url": {"type": "string", "description": "For 'navigate'"},
            "selector": {"type": "string", "description": "CSS selector for click/fill/extract"},
            "text": {"type": "string", "description": "For 'fill'"},
            "path": {"type": "string", "description": "Save path for 'screenshot'"},
            "wait_for": {"type": "string", "description": "Optional selector to wait for after navigate"},
        },
        "required": ["action"],
    },
)
def browser(
    action: str,
    url: str = "",
    selector: str = "",
    text: str = "",
    path: str = "",
    wait_for: str = "",
) -> str:
    try:
        if action == "close":
            _state.close()
            return "browser closed"

        page = _state.ensure()

        if action == "navigate":
            if not url:
                return "Error: 'url' required for navigate"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=10000)
                except Exception:
                    pass
            return f"Navigated to {page.url}. title: {page.title()[:100]}"

        if action == "extract_text":
            sel = selector or "body"
            el = page.query_selector(sel)
            if not el:
                return f"No element matches {sel!r}"
            txt = el.inner_text()[:10000]
            return txt

        if action == "extract_html":
            sel = selector or "html"
            el = page.query_selector(sel)
            if not el:
                return f"No element matches {sel!r}"
            return el.inner_html()[:15000]

        if action == "click":
            if not selector:
                return "Error: 'selector' required for click"
            page.click(selector, timeout=5000)
            return f"clicked {selector}"

        if action == "fill":
            if not (selector and text):
                return "Error: 'selector' and 'text' required for fill"
            page.fill(selector, text, timeout=5000)
            return f"filled {selector} with {len(text)} chars"

        if action == "screenshot":
            out = Path(path or "xirang_shot.png").expanduser()
            page.screenshot(path=str(out), full_page=True)
            return f"saved screenshot to {out}"

        return f"Unknown action: {action}"
    except Exception as e:
        return f"Browser error: {type(e).__name__}: {e}"


def maybe_register() -> bool:
    """Called when the tool module is imported. Returns True if playwright
    is importable; False means the tool exists but will fail on first call
    with a helpful message."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False
