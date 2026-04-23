"""Primitive tools — Read/Write/Edit/Bash/Grep/Glob.

Philosophy: the 6 primitives cover ~90% of agent tasks. No pre-written skills.
The agent composes these on the fly. Recipes (xirang.recipe) cache successful
compositions so repeated tasks skip planning.
"""
from __future__ import annotations

import csv
import concurrent.futures
import fnmatch
import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

# -------- tool registry --------

_TOOLS: dict[str, "Tool"] = {}


class Tool:
    __slots__ = ("name", "description", "schema", "handler")

    def __init__(self, name: str, description: str, schema: dict, handler: Callable):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler

    def to_anthropic(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def run(self, args: dict) -> str:
        try:
            return str(self.handler(**args))
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def tool(name: str, description: str, schema: dict):
    def deco(fn):
        _TOOLS[name] = Tool(name, description, schema, fn)
        return fn
    return deco


def all_tools() -> list[Tool]:
    return list(_TOOLS.values())


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


# -------- primitives --------

@tool(
    name="read_file",
    description="Read a file from disk. Returns the file contents as text.",
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "limit": {"type": "integer", "description": "Max lines to read (default 2000)"},
        },
        "required": ["path"],
    },
)
def read_file(path: str, limit: int = 2000) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"Error: {path} does not exist"
    if p.is_dir():
        return f"Error: {path} is a directory; use glob instead"
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()[:limit]
    return "\n".join(f"{i+1:>5}  {line}" for i, line in enumerate(lines))


@tool(
    name="write_file",
    description="Write (or overwrite) a file with the given content. Creates parent dirs.",
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {p}"


@tool(
    name="edit_file",
    description="Replace exactly one occurrence of old_text with new_text in a file.",
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        "required": ["path", "old_text", "new_text"],
    },
)
def edit_file(path: str, old_text: str, new_text: str) -> str:
    p = Path(path).expanduser()
    text = p.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count == 0:
        return f"Error: old_text not found in {path}"
    if count > 1:
        return f"Error: old_text appears {count} times in {path} — make it unique"
    p.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {p}"


@tool(
    name="bash",
    description="Run a shell command and return stdout+stderr. Use this for ANY system "
                "action: git, curl, python scripts, pip install, process management, etc. "
                "No need for dedicated 'skills' — just compose shell commands.",
    schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "description": "Seconds (default 30)"},
        },
        "required": ["command"],
    },
)
def bash(command: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out[:20000] if len(out) <= 20000 else out[:20000] + f"\n... [truncated, {len(out)} bytes total]"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"


@tool(
    name="grep",
    description="Search for a regex pattern in files under a directory. Returns matching lines.",
    schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Python regex"},
            "path": {"type": "string", "description": "Dir or file (default '.')"},
            "glob": {"type": "string", "description": "Filename glob, e.g. '*.py'"},
        },
        "required": ["pattern"],
    },
)
def grep(pattern: str, path: str = ".", glob: str = "*") -> str:
    rx = re.compile(pattern)
    root = Path(path).expanduser()
    hits: list[str] = []
    targets: list[Path] = []
    if root.is_file():
        targets = [root]
    else:
        for p in root.rglob(glob):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                targets.append(p)
    for fp in targets[:500]:
        try:
            for n, line in enumerate(fp.read_text(errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{fp}:{n}: {line[:200]}")
                    if len(hits) >= 200:
                        break
        except Exception:
            continue
        if len(hits) >= 200:
            break
    return "\n".join(hits) if hits else "No matches."


@tool(
    name="glob",
    description="List files matching a glob pattern.",
    schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "e.g. 'src/**/*.py'"},
            "path": {"type": "string", "description": "Base dir (default '.')"},
        },
        "required": ["pattern"],
    },
)
def glob(pattern: str, path: str = ".") -> str:
    root = Path(path).expanduser()
    results = [str(p) for p in root.glob(pattern) if p.is_file()]
    results.sort()
    return "\n".join(results[:300]) if results else "No matches."


@tool(
    name="write_and_run",
    description="Write an inline Python or shell script to a temp file and execute it. "
                "Use this when you need multi-line logic or computation — the agent's "
                "'do-anything' tool that replaces pre-written skills.",
    schema={
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["python", "bash"]},
            "code": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "required": ["language", "code"],
    },
)
def write_and_run(language: str, code: str, timeout: int = 60) -> str:
    import tempfile
    suffix = ".py" if language == "python" else ".sh"
    cmd_prefix = "python3" if language == "python" else "bash"
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run(
            f"{cmd_prefix} {path}", shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out[:20000] if len(out) <= 20000 else out[:20000] + "\n... [truncated]"
    except subprocess.TimeoutExpired:
        return f"Error: timed out after {timeout}s"
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


@tool(
    name="search_catalog",
    description="Search Xirang's local catalog of public APIs and free/local LLM providers. "
                "Use this before web-searching for APIs or model providers; successful finds can be reused.",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search terms, e.g. weather, maps, openrouter, free llm"},
            "kind": {"type": "string", "enum": ["all", "api", "llm"], "description": "Catalog kind"},
            "limit": {"type": "integer", "description": "Max results (default 8)"},
        },
        "required": ["query"],
    },
)
def search_catalog(query: str, kind: str = "all", limit: int = 8) -> str:
    from xirang import catalog
    home = Path(os.getenv("XIRANG_HOME") or (Path.home() / ".xirang")).expanduser()
    entries = catalog.search(home / "catalogs", query=query, kind=kind, limit=limit)
    return catalog.format_entries(entries)


def _truncate(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def _json_dumps(data: Any) -> str:
    return _truncate(json.dumps(data, ensure_ascii=False, indent=2))


def _json_path_tokens(query: str) -> list[str]:
    query = (query or "").strip()
    if not query:
        return []
    normalized = re.sub(r"\[(\d+)\]", r".\1", query)
    return [part for part in normalized.split(".") if part]


def _json_lookup(data: Any, query: str) -> Any:
    current = data
    for token in _json_path_tokens(query):
        if isinstance(current, list):
            current = current[int(token)]
            continue
        if isinstance(current, dict):
            current = current[token]
            continue
        raise KeyError(token)
    return current


@tool(
    name="http_request",
    description=(
        "Make an HTTP request for APIs, webhooks, health checks, and automation. "
        "Supports GET/POST/PUT/PATCH/DELETE, optional JSON body, custom headers, "
        "query params, and optional save-to-file for response bodies."
    ),
    schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL, e.g. https://api.example.com/data"},
            "method": {"type": "string", "description": "HTTP method (default GET)"},
            "headers": {
                "type": "object",
                "description": "Optional headers",
                "additionalProperties": {"type": "string"},
            },
            "params": {
                "type": "object",
                "description": "Query params appended to the URL",
                "additionalProperties": {"type": ["string", "number", "boolean"]},
            },
            "body": {"type": "string", "description": "Raw request body"},
            "json_body": {"type": "object", "description": "JSON request body"},
            "timeout": {"type": "integer", "description": "Timeout seconds (default 30)"},
            "save_path": {"type": "string", "description": "Optional path to save the response body"},
        },
        "required": ["url"],
    },
)
def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: str = "",
    json_body: dict[str, Any] | None = None,
    timeout: int = 30,
    save_path: str = "",
) -> str:
    method = (method or "GET").upper()
    headers = {str(k): str(v) for k, v in (headers or {}).items()}
    if params:
        parsed = urlparse.urlsplit(url)
        query = dict(urlparse.parse_qsl(parsed.query, keep_blank_values=True))
        query.update({str(k): str(v) for k, v in params.items()})
        url = urlparse.urlunsplit(parsed._replace(query=urlparse.urlencode(query)))

    data: bytes | None = None
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
    elif body:
        data = body.encode("utf-8")

    req = urlrequest.Request(url=url, method=method, data=data, headers=headers)
    try:
        with urlrequest.urlopen(req, timeout=max(int(timeout), 1)) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
            reason = getattr(resp, "reason", "OK")
            content_type = resp.headers.get("Content-Type", "")
            if save_path:
                out = Path(save_path).expanduser()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(raw)
                return _json_dumps(
                    {
                        "url": url,
                        "method": method,
                        "status": status,
                        "reason": str(reason),
                        "content_type": content_type,
                        "saved_to": str(out),
                        "bytes": len(raw),
                    }
                )
            charset = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            payload: Any = text
            if "json" in content_type.lower():
                try:
                    payload = json.loads(text)
                except Exception:
                    payload = text
            return _json_dumps(
                {
                    "url": url,
                    "method": method,
                    "status": status,
                    "reason": str(reason),
                    "content_type": content_type,
                    "body": payload,
                }
            )
    except urlerror.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return f"Error: HTTPError {e.code}: {_truncate(detail, 4000)}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@tool(
    name="json_query",
    description=(
        "Inspect JSON from inline text or a file path. Useful for pretty-printing, "
        "extracting nested fields, listing keys, and debugging API responses."
    ),
    schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["pretty", "get", "keys", "type"]},
            "text": {"type": "string", "description": "Inline JSON text"},
            "path": {"type": "string", "description": "Path to a JSON file"},
            "query": {"type": "string", "description": "Dot path like data.items[0].name"},
        },
        "required": ["action"],
    },
)
def json_query(action: str, text: str = "", path: str = "", query: str = "") -> str:
    if not text and not path:
        return "Error: provide either 'text' or 'path'"
    source = text
    if path:
        source = Path(path).expanduser().read_text(encoding="utf-8")
    data = json.loads(source)
    target = _json_lookup(data, query) if query else data
    if action == "pretty":
        return _json_dumps(target)
    if action == "get":
        return _json_dumps(target) if isinstance(target, (dict, list)) else str(target)
    if action == "keys":
        if not isinstance(target, dict):
            return f"Error: target at query '{query}' is not an object"
        return "\n".join(sorted(str(k) for k in target.keys()))
    if action == "type":
        return type(target).__name__
    return f"Error: unknown action: {action}"


def _sqlite_connect(path: str) -> sqlite3.Connection:
    p = Path(path).expanduser()
    uri = f"file:{p.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


@tool(
    name="sqlite_query",
    description=(
        "Read-only SQLite inspection tool. Useful for local app databases, caches, "
        "analytics snapshots, and exported data. Actions: tables, schema, query."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to a SQLite database file"},
            "action": {"type": "string", "enum": ["tables", "schema", "query"]},
            "table": {"type": "string", "description": "Table name for schema action"},
            "query": {"type": "string", "description": "SQL query for query action"},
            "limit": {"type": "integer", "description": "Max rows to return (default 50)"},
        },
        "required": ["path", "action"],
    },
)
def sqlite_query(path: str, action: str, table: str = "", query: str = "", limit: int = 50) -> str:
    limit = max(int(limit or 50), 1)
    with _sqlite_connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if action == "tables":
            rows = cur.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
            ).fetchall()
            return "\n".join(row["name"] for row in rows) or "No user tables."
        if action == "schema":
            if not table:
                return "Error: table is required for schema"
            rows = cur.execute(f"pragma table_info({table})").fetchall()
            if not rows:
                return f"Error: no such table: {table}"
            payload = [
                {
                    "cid": row["cid"],
                    "name": row["name"],
                    "type": row["type"],
                    "notnull": row["notnull"],
                    "default": row["dflt_value"],
                    "pk": row["pk"],
                }
                for row in rows
            ]
            return _json_dumps(payload)
        if action == "query":
            if not query:
                return "Error: query is required for query action"
            rows = cur.execute(query).fetchmany(limit)
            payload = [dict(row) for row in rows]
            return _json_dumps(payload)
    return f"Error: unknown action: {action}"


@tool(
    name="csv_query",
    description=(
        "Inspect CSV/TSV files without writing custom scripts. Actions: summary, head, "
        "filter_eq. Useful for exported reports, spreadsheets, logs, and tabular data."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to a CSV/TSV file"},
            "action": {"type": "string", "enum": ["summary", "head", "filter_eq"]},
            "delimiter": {"type": "string", "description": "Delimiter, default ','"},
            "limit": {"type": "integer", "description": "Max rows to return (default 20)"},
            "column": {"type": "string", "description": "Column name for filter_eq"},
            "equals": {"type": "string", "description": "Exact value for filter_eq"},
        },
        "required": ["path", "action"],
    },
)
def csv_query(
    path: str,
    action: str,
    delimiter: str = ",",
    limit: int = 20,
    column: str = "",
    equals: str = "",
) -> str:
    fp = Path(path).expanduser()
    limit = max(int(limit or 20), 1)
    with fp.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter or ",")
        columns = list(reader.fieldnames or [])
        if action == "summary":
            row_count = 0
            sample: list[dict[str, str]] = []
            for row in reader:
                row_count += 1
                if len(sample) < min(limit, 5):
                    sample.append(dict(row))
            return _json_dumps(
                {
                    "path": str(fp),
                    "columns": columns,
                    "row_count": row_count,
                    "sample": sample,
                }
            )
        if action == "head":
            rows: list[dict[str, str]] = []
            for row in reader:
                rows.append(dict(row))
                if len(rows) >= limit:
                    break
            return _json_dumps(rows)
        if action == "filter_eq":
            if not column:
                return "Error: column is required for filter_eq"
            rows = []
            for row in reader:
                if str(row.get(column, "")) == equals:
                    rows.append(dict(row))
                    if len(rows) >= limit:
                        break
            return _json_dumps(rows)
    return f"Error: unknown action: {action}"


# -------- subagent dispatch (lazy factory to avoid circular import) --------

_subagent_factory: Callable[[], Any] | None = None


def set_subagent_factory(fn: Callable[[], Any]) -> None:
    """Register the Agent factory from outside (cli.py or wherever Agent is created).

    We use a factory not an instance so each subagent gets a fresh message history.
    """
    global _subagent_factory
    _subagent_factory = fn


@tool(
    name="dispatch_subagent",
    description="Spawn a fresh subagent to handle an independent subtask in its own "
                "context (no message history bleed). Use for: parallel research, "
                "isolating a long exploration from the main conversation, or when "
                "you need a second opinion. The subagent has the same tools. "
                "Returns the subagent's final text output.",
    schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Self-contained task description. Include any context "
                               "the subagent needs — it sees no history.",
            },
            "max_iters": {
                "type": "integer",
                "description": "Max tool-use iterations (default 8)",
            },
        },
        "required": ["task"],
    },
)
def dispatch_subagent(task: str, max_iters: int = 8) -> str:
    if _subagent_factory is None:
        return "Error: subagent factory not registered"
    try:
        agent = _subagent_factory()
        # run quietly: no UI panels, no recipe recording (too noisy)
        result = agent.run_silent(task, max_iters=max_iters)
        return result or "(subagent returned no text)"
    except Exception as e:
        return f"Subagent error: {type(e).__name__}: {e}"


@tool(
    name="dispatch_subagent_batch",
    description=(
        "Run several independent subtasks with fresh subagents and return a structured "
        "summary. Useful for bounded parallel research, file-by-file analysis, or "
        "splitting a broad task into isolated explorations."
    ),
    schema={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Independent self-contained tasks; each subagent sees only its own task.",
            },
            "max_iters": {
                "type": "integer",
                "description": "Max tool-use iterations per subagent (default 8)",
            },
            "max_parallel": {
                "type": "integer",
                "description": "Max worker concurrency (default 3)",
            },
        },
        "required": ["tasks"],
    },
)
def dispatch_subagent_batch(tasks: list[str], max_iters: int = 8, max_parallel: int = 3) -> str:
    if _subagent_factory is None:
        return "Error: subagent factory not registered"
    items = [str(task).strip() for task in (tasks or []) if str(task).strip()]
    if not items:
        return "Error: tasks must contain at least one non-empty task"
    max_workers = max(1, min(int(max_parallel or 3), len(items), 8))

    def _run(task: str) -> dict[str, Any]:
        try:
            agent = _subagent_factory()
            output = agent.run_silent(task, max_iters=max_iters)
            return {"task": task, "ok": not str(output).startswith("Error:"), "output": output}
        except Exception as e:
            return {"task": task, "ok": False, "output": f"Subagent error: {type(e).__name__}: {e}"}

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_run, task): task for task in items}
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())
    results.sort(key=lambda row: items.index(row["task"]))
    return _json_dumps(
        {
            "task_count": len(items),
            "max_parallel": max_workers,
            "results": results,
        }
    )
