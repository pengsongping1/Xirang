"""Automation primitives for Xirang: cron-like jobs and webhook ingestion."""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import parse as urlparse

from xirang import audit
from xirang import session as sess
from xirang.agent import Agent
from xirang.config import Config


@dataclass
class CronJob:
    name: str
    schedule: str
    prompt: str
    session_name: str = ""
    enabled: bool = True
    next_run_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_run_at: float = 0.0
    last_status: str = ""
    last_output_excerpt: str = ""


@dataclass
class WebhookRoute:
    name: str
    token: str
    prompt_prefix: str = ""
    session_name: str = ""
    created_at: float = field(default_factory=time.time)
    last_used_at: float = 0.0


def _json_path(home: Path, section: str) -> Path:
    path = home / "automation" / f"{section}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_duration(raw: str) -> float:
    raw = raw.strip().lower()
    if not raw:
        raise ValueError("empty duration")
    unit = raw[-1]
    value = float(raw[:-1]) if unit.isalpha() else float(raw)
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    if unit.isdigit():
        return float(raw)
    raise ValueError(f"unsupported duration unit: {raw}")


def _next_run(schedule: str, now: float | None = None, *, last_run_at: float = 0.0) -> float:
    now = now or time.time()
    schedule = (schedule or "").strip().lower()
    if schedule.startswith("@every "):
        interval = _parse_duration(schedule[len("@every "):])
        base = last_run_at or now
        return base + interval
    if schedule == "@hourly":
        return (last_run_at or now) + 3600
    if schedule == "@daily":
        return (last_run_at or now) + 86400
    if schedule == "@weekly":
        return (last_run_at or now) + 7 * 86400
    if schedule.startswith("@once "):
        if last_run_at:
            return 0.0
        schedule = schedule[len("@once "):].strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            struct = time.strptime(schedule.replace("Z", ""), fmt)
            return time.mktime(struct)
        except ValueError:
            continue
    raise ValueError(
        "schedule must be @every <Ns|Nm|Nh|Nd>, @hourly, @daily, @weekly, or @once <YYYY-MM-DD HH:MM[:SS]>"
    )


def load_jobs(home: Path) -> list[CronJob]:
    return [CronJob(**row) for row in _load_rows(_json_path(home, "jobs"))]


def save_jobs(home: Path, jobs: list[CronJob]) -> None:
    _save_rows(_json_path(home, "jobs"), [asdict(job) for job in jobs])


def add_job(home: Path, name: str, schedule: str, prompt: str, session_name: str = "") -> CronJob:
    jobs = [job for job in load_jobs(home) if job.name != name]
    job = CronJob(
        name=name,
        schedule=schedule,
        prompt=prompt,
        session_name=session_name or f"cron-{name}",
        next_run_at=_next_run(schedule),
    )
    jobs.append(job)
    save_jobs(home, jobs)
    return job


def delete_job(home: Path, name: str) -> bool:
    jobs = load_jobs(home)
    kept = [job for job in jobs if job.name != name]
    if len(kept) == len(jobs):
        return False
    save_jobs(home, kept)
    return True


def list_jobs(home: Path) -> list[CronJob]:
    return sorted(load_jobs(home), key=lambda job: (job.next_run_at or 0, job.name))


def _restore_agent(cfg: Config, session_name: str) -> Agent:
    agent = Agent(cfg)
    blob = sess.load(cfg.home, session_name)
    if blob:
        sess.apply_to_agent(blob, agent)
    agent.current_session_name = session_name
    return agent


def run_job(cfg: Config, job_name: str) -> dict[str, Any]:
    jobs = load_jobs(cfg.home)
    target = next((job for job in jobs if job.name == job_name), None)
    if not target:
        raise ValueError(f"no job named '{job_name}'")
    agent = _restore_agent(cfg, target.session_name or f"cron-{target.name}")
    turn = agent.turn(target.prompt)
    sess.save(cfg.home, agent.current_session_name, agent)
    now = time.time()
    target.last_run_at = now
    target.last_status = "ok" if turn.success else "failed"
    target.last_output_excerpt = (turn.text_output or "")[:240]
    target.next_run_at = _next_run(target.schedule, now=now, last_run_at=now)
    if target.next_run_at <= 0:
        target.enabled = False
    save_jobs(cfg.home, jobs)
    audit.record(
        cfg.audit_path,
        "cron_run",
        {
            "job": target.name,
            "session": target.session_name,
            "success": turn.success,
            "next_run_at": target.next_run_at,
        },
    )
    return {
        "job": target.name,
        "session": target.session_name,
        "success": turn.success,
        "output": turn.text_output,
        "next_run_at": target.next_run_at,
    }


def run_due_jobs(cfg: Config, *, now: float | None = None) -> list[dict[str, Any]]:
    now = now or time.time()
    results: list[dict[str, Any]] = []
    for job in list_jobs(cfg.home):
        if not job.enabled:
            continue
        if job.next_run_at and job.next_run_at > now:
            continue
        results.append(run_job(cfg, job.name))
    return results


def scheduler_loop(cfg: Config, *, poll_seconds: float = 30.0, max_loops: int = 0) -> None:
    loops = 0
    while True:
        run_due_jobs(cfg)
        loops += 1
        if max_loops and loops >= max_loops:
            return
        time.sleep(max(float(poll_seconds), 1.0))


def load_routes(home: Path) -> list[WebhookRoute]:
    return [WebhookRoute(**row) for row in _load_rows(_json_path(home, "webhooks"))]


def save_routes(home: Path, routes: list[WebhookRoute]) -> None:
    _save_rows(_json_path(home, "webhooks"), [asdict(route) for route in routes])


def add_route(home: Path, name: str, prompt_prefix: str = "", session_name: str = "", token: str = "") -> WebhookRoute:
    routes = [route for route in load_routes(home) if route.name != name]
    route = WebhookRoute(
        name=name,
        token=token or secrets.token_urlsafe(18),
        prompt_prefix=prompt_prefix,
        session_name=session_name or f"webhook-{name}",
    )
    routes.append(route)
    save_routes(home, routes)
    return route


def delete_route(home: Path, name: str) -> bool:
    routes = load_routes(home)
    kept = [route for route in routes if route.name != name]
    if len(kept) == len(routes):
        return False
    save_routes(home, kept)
    return True


def _payload_prompt(route: WebhookRoute, payload: Any) -> str:
    prefix = route.prompt_prefix.strip() or "Handle this webhook event. Summarize what happened and take any useful local follow-up actions."
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return f"{prefix}\n\nWebhook route: {route.name}\nPayload:\n{body}"


def _make_webhook_handler(cfg: Config):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XirangWebhook/0.1"

        def do_POST(self):  # noqa: N802
            parsed = urlparse.urlsplit(self.path)
            name = parsed.path.split("/")[-1].strip()
            query = urlparse.parse_qs(parsed.query)
            token = query.get("token", [""])[0] or self.headers.get("X-Xirang-Token", "")
            routes = load_routes(cfg.home)
            route = next((item for item in routes if item.name == name), None)
            if not route:
                self._send(404, {"ok": False, "error": f"unknown route: {name}"})
                return
            if token != route.token:
                self._send(403, {"ok": False, "error": "invalid token"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            content_type = self.headers.get("Content-Type", "")
            try:
                if "application/json" in content_type.lower():
                    payload: Any = json.loads(raw.decode("utf-8", errors="replace") or "{}")
                else:
                    payload = raw.decode("utf-8", errors="replace")
            except Exception:
                payload = raw.decode("utf-8", errors="replace")
            agent = _restore_agent(cfg, route.session_name or f"webhook-{route.name}")
            turn = agent.turn(_payload_prompt(route, payload))
            sess.save(cfg.home, agent.current_session_name, agent)
            route.last_used_at = time.time()
            save_routes(cfg.home, routes)
            audit.record(
                cfg.audit_path,
                "webhook_event",
                {
                    "route": route.name,
                    "session": route.session_name,
                    "success": turn.success,
                    "payload_type": type(payload).__name__,
                },
            )
            self._send(
                200,
                {
                    "ok": True,
                    "route": route.name,
                    "session": route.session_name,
                    "success": turn.success,
                    "output": turn.text_output,
                },
            )

        def do_GET(self):  # noqa: N802
            parsed = urlparse.urlsplit(self.path)
            if parsed.path.rstrip("/") == "/healthz":
                self._send(200, {"ok": True, "service": "xirang-webhooks"})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "routes": [
                        {"name": route.name, "session_name": route.session_name, "last_used_at": route.last_used_at}
                        for route in load_routes(cfg.home)
                    ],
                },
            )

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve_webhooks(cfg: Config, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, int(port)), _make_webhook_handler(cfg))
    try:
        server.serve_forever()
    finally:
        server.server_close()
