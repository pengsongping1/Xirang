"""Local benchmark harness for Xirang."""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

from xirang.agent import Agent
from xirang.config import Config


@dataclass
class BenchTask:
    name: str
    prompt: str | list[str]
    setup: Callable[[Path, contextlib.ExitStack], dict[str, Any]]
    evaluate: Callable[[Path, dict[str, Any], Agent, list[str]], tuple[bool, str]]
    description: str = ""


@dataclass
class BenchResult:
    name: str
    passed: bool
    detail: str
    turns: int
    duration_sec: float
    usage: dict[str, int] = field(default_factory=dict)


def _json_file(workspace: Path, name: str, payload: dict[str, Any]) -> Path:
    fp = workspace / name
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fp


def _start_json_server(payload: dict[str, Any]) -> tuple[HTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_port


def default_tasks() -> list[BenchTask]:
    def setup_json(workspace: Path, stack: contextlib.ExitStack) -> dict[str, Any]:
        fp = _json_file(workspace, "article.json", {"title": "Quarterly Planning", "owner": "ops"})
        return {"json": fp}

    def eval_json(workspace: Path, ctx: dict[str, Any], agent: Agent, outputs: list[str]) -> tuple[bool, str]:
        combined = "\n".join(outputs)
        passed = "Quarterly Planning" in combined
        return passed, "must mention JSON title 'Quarterly Planning'"

    def setup_csv(workspace: Path, stack: contextlib.ExitStack) -> dict[str, Any]:
        fp = workspace / "invoices.csv"
        fp.write_text("id,status,amount\nA1,paid,10\nA2,pending,5\nA3,paid,8\n", encoding="utf-8")
        return {"csv": fp, "result": workspace / "paid_ids.txt"}

    def eval_csv(workspace: Path, ctx: dict[str, Any], agent: Agent, outputs: list[str]) -> tuple[bool, str]:
        fp = ctx["result"]
        if not fp.exists():
            return False, "expected paid_ids.txt to be created"
        lines = [line.strip() for line in fp.read_text(encoding="utf-8").splitlines() if line.strip()]
        return lines == ["A1", "A3"], "paid_ids.txt should contain A1 and A3"

    def setup_sqlite(workspace: Path, stack: contextlib.ExitStack) -> dict[str, Any]:
        fp = workspace / "users.db"
        conn = sqlite3.connect(fp)
        conn.execute("create table users (id integer primary key, name text, status text)")
        conn.execute("insert into users (name, status) values ('alice', 'active'), ('bob', 'inactive'), ('cara', 'active')")
        conn.commit()
        conn.close()
        return {"db": fp}

    def eval_sqlite(workspace: Path, ctx: dict[str, Any], agent: Agent, outputs: list[str]) -> tuple[bool, str]:
        combined = "\n".join(outputs).lower()
        return "2" in combined and "active" in combined, "must report 2 active users"

    def setup_http(workspace: Path, stack: contextlib.ExitStack) -> dict[str, Any]:
        server, port = _start_json_server({"service": "demo", "status": "green"})
        stack.callback(server.shutdown)
        stack.callback(server.server_close)
        return {"url": f"http://127.0.0.1:{port}/health"}

    def eval_http(workspace: Path, ctx: dict[str, Any], agent: Agent, outputs: list[str]) -> tuple[bool, str]:
        combined = "\n".join(outputs).lower()
        return "demo" in combined and "green" in combined, "must mention demo service and green status"

    def setup_memory(workspace: Path, stack: contextlib.ExitStack) -> dict[str, Any]:
        return {}

    def eval_memory(workspace: Path, ctx: dict[str, Any], agent: Agent, outputs: list[str]) -> tuple[bool, str]:
        return "pnpm" in outputs[-1].lower(), "must recall pnpm on second turn"

    return [
        BenchTask(
            name="json_title_extract",
            description="Read local JSON and extract a nested field.",
            prompt="当前目录有 article.json。请读取它，并告诉我 title 字段的值。",
            setup=setup_json,
            evaluate=eval_json,
        ),
        BenchTask(
            name="csv_filter_write",
            description="Filter CSV rows and write a result file.",
            prompt="当前目录有 invoices.csv。请找出 status=paid 的 id，并写入 paid_ids.txt，每行一个 id，然后简单告诉我完成了。",
            setup=setup_csv,
            evaluate=eval_csv,
        ),
        BenchTask(
            name="sqlite_active_count",
            description="Inspect a SQLite database and summarize a count.",
            prompt="当前目录有 users.db。请查询 active 用户数量，并用一句话告诉我结果。",
            setup=setup_sqlite,
            evaluate=eval_sqlite,
        ),
        BenchTask(
            name="http_local_health",
            description="Call a local HTTP endpoint and summarize the payload.",
            prompt=["我会给你一个本地接口地址。", "请访问 {url}，并告诉我 service 和 status。"],
            setup=setup_http,
            evaluate=eval_http,
        ),
        BenchTask(
            name="memory_followup",
            description="Remember a rule across turns and recall it.",
            prompt=["记住，我们默认用 pnpm，不用 npm。", "我们默认用什么包管理器？只回答名字。"],
            setup=setup_memory,
            evaluate=eval_memory,
        ),
    ]


def run_benchmark(cfg: Config, *, dry_run: bool = False, out_path: Path | None = None) -> dict[str, Any]:
    tasks = default_tasks()
    if dry_run:
        result = {
            "dry_run": True,
            "task_count": len(tasks),
            "tasks": [{"name": task.name, "description": task.description} for task in tasks],
        }
        if out_path:
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    results: list[BenchResult] = []
    for task in tasks:
        with tempfile.TemporaryDirectory(prefix=f"xirang-bench-{task.name}-") as tmp:
            workspace = Path(tmp)
            with contextlib.ExitStack() as stack:
                ctx = task.setup(workspace, stack)
                prompts = task.prompt if isinstance(task.prompt, list) else [task.prompt]
                agent = Agent(cfg)
                agent.current_session_name = f"bench-{task.name}"
                outputs: list[str] = []
                started = time.time()
                old_cwd = Path.cwd()
                os.chdir(workspace)
                try:
                    for prompt in prompts:
                        prompt_text = prompt.format(**ctx) if "{" in prompt else prompt
                        turn = agent.turn(prompt_text)
                        outputs.append(turn.text_output)
                finally:
                    os.chdir(old_cwd)
                passed, detail = task.evaluate(workspace, ctx, agent, outputs)
                results.append(
                    BenchResult(
                        name=task.name,
                        passed=passed,
                        detail=detail,
                        turns=len(prompts),
                        duration_sec=round(time.time() - started, 2),
                        usage={k: int(v) for k, v in agent.total_usage.items()},
                    )
                )

    summary = {
        "dry_run": False,
        "provider": cfg.provider,
        "model": cfg.model,
        "passed": sum(1 for item in results if item.passed),
        "failed": sum(1 for item in results if not item.passed),
        "task_count": len(results),
        "results": [asdict(item) for item in results],
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
