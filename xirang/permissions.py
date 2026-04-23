"""Permission modes for tool execution.

Modes:
- auto: run tools without asking.
- default: same as auto, kept for backward compatibility.
- plan: read-only; blocks mutation/system/browser/subagent tools.
- ask: allow read tools; ask on a TTY before risky tools, otherwise deny.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass


READ_TOOLS = {
    "read_file",
    "grep",
    "glob",
    "search_catalog",
    "json_query",
    "sqlite_query",
    "csv_query",
}
RISKY_TOOLS = {
    "write_file",
    "edit_file",
    "bash",
    "write_and_run",
    "browser",
    "desktop",
    "dispatch_subagent",
    "dispatch_subagent_batch",
}


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str
    category: str
    risk: str = "low"


def tool_category(tool_name: str) -> str:
    if tool_name in READ_TOOLS:
        return "read"
    if tool_name in RISKY_TOOLS:
        return "action"
    if tool_name == "http_request":
        return "network"
    return "unknown"


_LOW_RISK_BASH = (
    "cat ",
    "ls",
    "pwd",
    "rg ",
    "grep ",
    "find ",
    "head ",
    "tail ",
    "sed -n",
    "wc ",
    "printf ",
    "echo ",
    "sort ",
)
_HIGH_RISK_PATTERNS = [
    r"\brm\s+-",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bkillall\b",
    r"\bpkill\b",
    r"\buseradd\b",
    r"\bpasswd\b",
    r"\bsudo\b",
    r"\bcurl\b[^\n|>]*\|[^\n]*\b(sh|bash)\b",
    r"\bwget\b[^\n|>]*\|[^\n]*\b(sh|bash)\b",
    r">\s*/etc/",
    r"\bchmod\b.*\s-R\b",
    r"\bchown\b.*\s-R\b",
]


def _contains_high_risk(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _HIGH_RISK_PATTERNS)


def risk_level(tool_name: str, args: dict) -> str:
    if tool_name in READ_TOOLS:
        return "low"
    if tool_name == "http_request":
        method = str(args.get("method", "GET")).upper()
        return "low" if method in {"GET", "HEAD", "OPTIONS"} else "medium"
    if tool_name in {"write_file", "edit_file", "dispatch_subagent", "dispatch_subagent_batch"}:
        return "medium"
    if tool_name == "browser":
        action = str(args.get("action", "")).lower()
        return "medium" if action in {"navigate", "extract_text", "extract_html", "screenshot", "close"} else "high"
    if tool_name == "desktop":
        action = str(args.get("action", "")).lower()
        return "medium" if action in {"status", "screenshot", "watch"} else "high"
    if tool_name == "bash":
        command = str(args.get("command", "")).strip()
        if not command:
            return "medium"
        if _contains_high_risk(command):
            return "high"
        lowered = command.lower()
        if any(lowered.startswith(prefix) for prefix in _LOW_RISK_BASH):
            return "low"
        return "medium"
    if tool_name == "write_and_run":
        code = str(args.get("code", ""))
        if _contains_high_risk(code):
            return "high"
        if any(token in code for token in ("subprocess", "os.remove", "os.unlink", "shutil.rmtree", "requests.post", "urlopen(")):
            return "high"
        return "medium"
    return "medium"


def decide(mode: str, tool_name: str, args: dict) -> PermissionDecision:
    mode = (mode or "default").lower()
    category = tool_category(tool_name)
    risk = risk_level(tool_name, args)
    if tool_name == "http_request":
        method = str(args.get("method", "GET")).upper()
        category = "read" if method in {"GET", "HEAD", "OPTIONS"} else "action"

    if mode in {"default", "auto"}:
        return PermissionDecision(True, f"mode={mode}", category, risk)

    if mode == "safe":
        if risk == "low":
            return PermissionDecision(True, "safe mode allows only low-risk tools", category, risk)
        return PermissionDecision(False, f"safe mode blocks {tool_name} ({risk} risk)", category, risk)

    if mode == "plan":
        if category == "read":
            return PermissionDecision(True, "plan mode allows read-only tools", category, risk)
        return PermissionDecision(False, f"plan mode blocks {tool_name}", category, risk)

    if mode == "ask":
        if risk == "low":
            return PermissionDecision(True, "ask mode auto-allows low-risk tools", category, risk)
        if not sys.stdin.isatty():
            return PermissionDecision(False, f"ask mode cannot confirm {tool_name} without a TTY", category, risk)
        prompt = f"Allow {risk}-risk tool `{tool_name}` with args keys {sorted(args.keys())}? [y/N] "
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            return PermissionDecision(False, f"ask mode confirmation failed for {tool_name}", category, risk)
        if answer in {"y", "yes"}:
            return PermissionDecision(True, "user approved", category, risk)
        return PermissionDecision(False, "user denied", category, risk)

    return PermissionDecision(False, f"unknown mode={mode}", category, risk)
