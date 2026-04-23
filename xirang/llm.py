"""LLM wrapper — Anthropic native + OpenAI-compatible (GPT/DeepSeek).

Features:
- Streaming text with optional on_text callback (live UI output)
- Automatic retry with exponential backoff for 5xx / 429
- Anthropic: prompt caching + adaptive thinking + 1M context beta
- OpenAI-compat: standard tool-call streaming assembly
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from xirang.config import Config
from xirang.tools import Tool


OnText = Callable[[str], None] | None


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    raw_assistant_content: Any = None
    usage: dict = field(default_factory=dict)


def _retry(fn, *, max_attempts: int = 4, base_delay: float = 1.0):
    """Retry a callable on 5xx / 429 with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            code = getattr(e, "status_code", None) or getattr(
                getattr(e, "response", None), "status_code", None
            )
            retryable = code in (429, 500, 502, 503, 504) or "timeout" in str(e).lower()
            if not retryable or attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), 30.0)
            time.sleep(delay)
    if last_exc:
        raise last_exc


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if cfg.is_anthropic:
            import anthropic
            kw: dict = {"api_key": cfg.api_key}
            if cfg.base_url:
                kw["base_url"] = cfg.base_url
            self.client = anthropic.Anthropic(**kw)
        else:
            from openai import OpenAI
            kw = {"api_key": cfg.api_key}
            if cfg.base_url:
                kw["base_url"] = cfg.base_url
            self.client = OpenAI(**kw)

    # ---- public ----
    def chat(
        self,
        messages: list[dict],
        system: str,
        tools: list[Tool],
        max_tokens: int = 4096,
        on_text: OnText = None,
    ) -> ChatResult:
        if self.cfg.is_anthropic:
            return _retry(lambda: self._chat_anthropic(messages, system, tools, max_tokens, on_text))
        return _retry(lambda: self._chat_openai(messages, system, tools, max_tokens, on_text))

    # ---- anthropic ----
    def _chat_anthropic(
        self, messages: list[dict], system: str, tools: list[Tool],
        max_tokens: int, on_text: OnText,
    ) -> ChatResult:
        tool_schemas = [t.to_anthropic() for t in tools]
        system_blocks = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        kwargs: dict = {
            "model": self.cfg.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
            "tools": tool_schemas,
            "extra_headers": {"anthropic-beta": "context-1m-2025-08-07"},
        }
        if "opus-4" in self.cfg.model or "sonnet-4-6" in self.cfg.model:
            kwargs["thinking"] = {"type": "adaptive"}

        if on_text is None:
            resp = self.client.messages.create(**kwargs)
            return self._build_result_from_anthropic(resp)

        # Streaming path
        with self.client.messages.stream(**kwargs) as stream:
            for text_chunk in stream.text_stream:
                if text_chunk:
                    on_text(text_chunk)
            final = stream.get_final_message()
        return self._build_result_from_anthropic(final)

    def _build_result_from_anthropic(self, resp) -> ChatResult:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, args=block.input))
        return ChatResult(
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason or "",
            raw_assistant_content=resp.content,
            usage={
                "input": resp.usage.input_tokens,
                "output": resp.usage.output_tokens,
                "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0),
                "cache_create": getattr(resp.usage, "cache_creation_input_tokens", 0),
            },
        )

    # ---- openai / deepseek ----
    def _chat_openai(
        self, messages: list[dict], system: str, tools: list[Tool],
        max_tokens: int, on_text: OnText,
    ) -> ChatResult:
        oai_msgs = self._convert_messages_to_openai(system, messages)
        tool_param = [t.to_openai() for t in tools] or None

        if on_text is None:
            resp = self.client.chat.completions.create(
                model=self.cfg.model,
                messages=oai_msgs,
                tools=tool_param,
                max_tokens=max_tokens,
            )
            return self._build_result_from_openai_nonstream(resp)

        # Streaming path — accumulate text + tool calls by index
        stream = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=oai_msgs,
            tools=tool_param,
            max_tokens=max_tokens,
            stream=True,
        )
        text_buf: list[str] = []
        tc_buf: dict[int, dict] = {}  # index -> {id, name, args_str}
        finish_reason = ""
        usage_info = {}
        for chunk in stream:
            if chunk.usage:
                usage_info = {
                    "input": chunk.usage.prompt_tokens,
                    "output": chunk.usage.completion_tokens,
                }
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if delta.content:
                text_buf.append(delta.content)
                on_text(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    slot = tc_buf.setdefault(idx, {"id": "", "name": "", "args_str": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["args_str"] += tc.function.arguments

        text = "".join(text_buf)
        tool_calls: list[ToolCall] = []
        for idx in sorted(tc_buf.keys()):
            slot = tc_buf[idx]
            try:
                args = json.loads(slot["args_str"] or "{}")
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=slot["id"] or f"tc_{idx}", name=slot["name"], args=args))

        raw: list[dict] = []
        if text:
            raw.append({"type": "text", "text": text})
        for tc in tool_calls:
            raw.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.args})
        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            stop_reason=finish_reason,
            raw_assistant_content=raw,
            usage=usage_info,
        )

    def _build_result_from_openai_nonstream(self, resp) -> ChatResult:
        msg = resp.choices[0].message
        tcs: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                tcs.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
        raw: list[dict] = []
        if msg.content:
            raw.append({"type": "text", "text": msg.content})
        for tc in tcs:
            raw.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.args})
        return ChatResult(
            text=msg.content or "",
            tool_calls=tcs,
            stop_reason=resp.choices[0].finish_reason or "",
            raw_assistant_content=raw,
            usage={
                "input": resp.usage.prompt_tokens if resp.usage else 0,
                "output": resp.usage.completion_tokens if resp.usage else 0,
            },
        )

    def _convert_messages_to_openai(self, system: str, messages: list[dict]) -> list[dict]:
        """Unified internal → OpenAI flat message list."""
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            role = m["role"]
            content = m.get("content")
            if role == "user" and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        out.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": str(item.get("content", "")),
                        })
                    else:
                        out.append({"role": "user", "content": str(item)})
            elif role == "assistant" and isinstance(content, list):
                text_parts, tcs = [], []
                for item in content:
                    t = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
                    if t == "text":
                        text_parts.append(getattr(item, "text", None) or item.get("text", ""))
                    elif t == "tool_use":
                        tcs.append({
                            "id": getattr(item, "id", None) or item.get("id"),
                            "type": "function",
                            "function": {
                                "name": getattr(item, "name", None) or item.get("name"),
                                "arguments": json.dumps(
                                    getattr(item, "input", None) or item.get("input", {})
                                ),
                            },
                        })
                msg: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
                if tcs:
                    msg["tool_calls"] = tcs
                out.append(msg)
            else:
                out.append({"role": role, "content": content})
        return out

    # ---- one-shot text completion (no tools, no streaming) ----
    def complete(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        res = self.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system or "You are a helpful assistant.",
            tools=[],
            max_tokens=max_tokens,
        )
        return res.text
