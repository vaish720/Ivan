"""LLM providers behind one interface.

Groq and Ollama both speak the OpenAI chat-completions format, so one client covers
both. FallbackLLM switches to the local model when the free cloud tier runs out.
"""

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    """Rate-limited, unreachable or not configured: worth switching provider."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AssistantTurn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    def as_message(self) -> dict:
        message: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in self.tool_calls
            ]
        return message


class LLM(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn: ...


class OpenAICompatibleLLM:
    def __init__(self, name: str, base_url: str, model: str, api_key: str = "", timeout: float = 180):
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        if self.name == "groq" and not self._api_key:
            raise LLMUnavailable("GROQ_API_KEY is not set")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        body = {"model": self._model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0}
        try:
            response = httpx.post(self._url, json=body, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"{self.name} unreachable: {exc}") from exc
        if response.status_code == 429:
            raise LLMUnavailable(f"{self.name} rate limit reached")
        if response.status_code >= 400:
            raise LLMError(f"{self.name} returned {response.status_code}: {response.text[:300]}")
        return parse_message(response.json()["choices"][0]["message"])


def parse_message(message: dict) -> AssistantTurn:
    calls = []
    for raw in message.get("tool_calls") or []:
        fn = raw["function"]
        args = fn.get("arguments") or "{}"
        try:
            parsed = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            parsed = {}
        calls.append(ToolCall(raw.get("id") or f"call_{uuid.uuid4().hex[:8]}", fn["name"], parsed or {}))
    content = _THINK.sub("", message.get("content") or "").strip()
    return AssistantTurn(content, calls)


class FallbackLLM:
    """Uses the primary model until it is unavailable, then stays on the fallback."""

    def __init__(self, primary: LLM, fallback: LLM, on_switch: Callable[[str], None] = lambda reason: None):
        self._primary = primary
        self._fallback = fallback
        self._on_switch = on_switch
        self.switched_reason: str | None = None

    @property
    def name(self) -> str:
        return self._fallback.name if self.switched_reason else self._primary.name

    @property
    def notice(self) -> str | None:
        if self.switched_reason:
            return f"Using the slower local model ({self.switched_reason})."
        return None

    def complete(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        if not self.switched_reason:
            try:
                return self._primary.complete(messages, tools)
            except LLMUnavailable as exc:
                self.switched_reason = str(exc)
                self._on_switch(str(exc))
        return self._fallback.complete(messages, tools)
