"""Chat-model interface (native tool calling) plus a scripted fake and an OpenAI-compatible adapter.

The OpenAI-compatible adapter works with OpenAI, Groq (``https://api.groq.com/openai/v1``),
Ollama, vLLM and other servers that implement the chat-completions API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolRequest:
    call_id: str
    tool: str
    args: dict[str, Any] | None  # None => the model produced invalid JSON


@dataclass(frozen=True)
class ModelTurn:
    content: str = ""
    requests: tuple[ToolRequest, ...] = field(default_factory=tuple)


class ChatModel(Protocol):
    def next_turn(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]) -> ModelTurn: ...


class FakeChatModel:
    """Replays a script of turns (or exceptions), or delegates to a function. Records every request."""

    def __init__(self, script: Sequence[ModelTurn | Exception] | Callable[..., ModelTurn]) -> None:
        self.script = script if callable(script) else list(script)
        self.seen: list[list[dict[str, Any]]] = []
        self.seen_tools: list[list[str]] = []

    def next_turn(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]) -> ModelTurn:
        self.seen.append([dict(m) for m in messages])
        self.seen_tools.append([t["name"] for t in tools])
        if callable(self.script):
            return self.script(messages, tools)
        if not self.script:
            raise ModelError("fake script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _decode_args(raw: str | None) -> dict[str, Any] | None:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _wire_message(message: dict[str, Any]) -> dict[str, Any]:
    if message["role"] == "assistant" and message.get("requests"):
        return {"role": "assistant", "content": message.get("content") or None,
                "tool_calls": [{"id": r.call_id, "type": "function",
                                "function": {"name": r.tool, "arguments": json.dumps(r.args or {})}}
                               for r in message["requests"]]}
    if message["role"] == "tool":
        return {"role": "tool", "tool_call_id": message["call_id"], "content": message["content"]}
    return {"role": message["role"], "content": message["content"]}


class OpenAICompatModel:
    def __init__(self, model: str, *, api_key: str | None = None, base_url: str | None = None,
                 client: Any = None, timeout: float = 30.0) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - optional extra
                raise ModelError("install the optional extra: pip install 'retailia[openai]'") from exc
            client = OpenAI(api_key=api_key or "unused-for-local-servers", base_url=base_url, timeout=timeout)
        self.client = client
        self.model = model

    def next_turn(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]) -> ModelTurn:
        try:
            response = self.client.chat.completions.create(
                model=self.model, temperature=0,
                messages=[_wire_message(m) for m in messages],
                tools=[{"type": "function", "function": t} for t in tools] or None,
            )
            msg = response.choices[0].message
        except Exception as exc:
            raise ModelError(f"model request failed ({type(exc).__name__})") from exc
        requests = tuple(ToolRequest(c.id, c.function.name, _decode_args(c.function.arguments))
                         for c in (msg.tool_calls or []))
        return ModelTurn(content=msg.content or "", requests=requests)
