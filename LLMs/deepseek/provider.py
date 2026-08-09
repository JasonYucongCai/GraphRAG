"""
LLMs/deepseek/provider.py — DeepSeek LLM provider (IPP).

Wraps the OpenAI SDK against DeepSeek's OpenAI-compatible Chat Completions
endpoint. The LLM provider is itself an IPP — Φ performs the transformer
inference:

  LLMProvider: (messages + tools) → Φ → ChatCompletion-like result

Exposes: LLMResult (envelope), DeepSeekProvider (live), MockProvider (offline).
Models: deepseek-v4-flash (fast, non-thinking) / deepseek-v4-pro (thinking).
"""
from __future__ import annotations

import logging
from typing import Optional

from general_tools.config import Config
from general_tools.IPP import IPP

logger = logging.getLogger("LLMs.deepseek.provider")


class LLMResult:
    """Minimal ChatCompletion-like envelope (choices[0].message, usage)."""

    def __init__(self, content: str, tool_calls: Optional[list] = None,
                 usage: Optional[dict] = None, thinking: Optional[str] = None):
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.usage = usage or {}
        self.thinking = thinking  # reasoning_content (DeepSeek thinking mode)

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)


class DeepSeekProvider(IPP):
    """
    Chat Completions provider for DeepSeek V4.

    Usage:
        llm = DeepSeekProvider()
        result = llm.chat(messages=[...], tools=[...], temperature=0.3)
        result.content        # text answer
        result.tool_calls     # [{id, function:{name, arguments}}]
    """

    name = "deepseek"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, max_retries: int = 2):
        super().__init__()
        self.model = model or Config.get_model()
        self.api_key = api_key or Config.api_key()
        self.base_url = base_url or Config.DEEPSEEK_BASE_URL
        self.max_retries = max_retries
        self._client = None
        self.name = f"deepseek:{self.model}"

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def switch_model(self, model_id: str) -> None:
        self.model = model_id
        self.name = f"deepseek:{model_id}"

    # ── IPP transform: (messages, tools) → result ─────────────────────────
    def transform(self, inp: dict) -> LLMResult:
        messages = inp["messages"]
        tools = inp.get("tools")
        temperature = inp.get("temperature", Config.TEMPERATURE)
        max_tokens = inp.get("max_tokens", Config.MAX_TOKENS)
        return self.chat(messages=messages, tools=tools,
                         temperature=temperature, max_tokens=max_tokens)

    def chat(self, messages: list, tools: Optional[list] = None,
             temperature: float = Config.TEMPERATURE,
             max_tokens: int = Config.MAX_TOKENS,
             stream: bool = False) -> LLMResult:
        """Non-streaming Chat Completions call (self-contained)."""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if "flash" in self.model:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif "v4-pro" in self.model and Config.DEEPSEEK_THINKING:
            kwargs["extra_body"] = {
                "thinking": {"type": "enabled"},
                "reasoning_effort": Config.DEEPSEEK_THINKING,
            }

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message
                tool_calls = []
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tool_calls.append({
                            "id": tc.id,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "",
                            },
                        })
                usage = {}
                if getattr(resp, "usage", None):
                    usage = {
                        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
                        "total_tokens": getattr(resp.usage, "total_tokens", 0),
                    }
                thinking = getattr(msg, "reasoning_content", None) or ""
                return LLMResult(content=msg.content or "", tool_calls=tool_calls,
                                 usage=usage, thinking=thinking)
            except Exception as exc:  # noqa: BLE001 — retry with backoff
                last_err = exc
                logger.warning("DeepSeek call failed (attempt %d): %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    import time
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"DeepSeek API failed after {self.max_retries + 1} attempts: {last_err}")

    def chat_stream(self, messages: list, tools: Optional[list] = None,
                    temperature: float = Config.TEMPERATURE,
                    max_tokens: int = Config.MAX_TOKENS):
        """
        STREAMING Chat Completions. Yields tuples as tokens arrive:

          ("thinking", str)   — reasoning_content delta (when enabled)
          ("text", str)       — content delta (assistant text, incremental)
          ("tool_delta", dict)— tool-call accumulation (name/arguments chunks)
          ("usage", int)      — total tokens (final chunk)

        After the stream ends, returns the accumulated LLMResult via the
        generator's return value (PEP 380) — same shape as chat().
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if "flash" in self.model:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif "v4-pro" in self.model and Config.DEEPSEEK_THINKING:
            kwargs["extra_body"] = {
                "thinking": {"type": "enabled"},
                "reasoning_effort": Config.DEEPSEEK_THINKING,
            }

        collected_content = ""
        collected_thinking = ""
        collected_tool_calls: list[dict] = []
        usage_total = 0

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — surface to caller
            logger.error("DeepSeek stream start failed: %s", exc)
            raise

        for chunk in response:
            if getattr(chunk, "usage", None):
                usage_total = chunk.usage.total_tokens
                yield ("usage", usage_total)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            # reasoning / thinking content
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                collected_thinking += rc
                yield ("thinking", rc)
            if delta.content:
                collected_content += delta.content
                yield ("text", delta.content)
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = tc.index
                    while len(collected_tool_calls) <= idx:
                        collected_tool_calls.append({
                            "id": "", "function": {"name": "", "arguments": ""},
                        })
                    if tc.id:
                        collected_tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            collected_tool_calls[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            collected_tool_calls[idx]["function"]["arguments"] += tc.function.arguments
                            yield ("tool_delta", {
                                "index": idx,
                                "arguments": tc.function.arguments,
                            })

        return LLMResult(
            content=collected_content,
            tool_calls=collected_tool_calls,
            usage={"prompt_tokens": 0, "completion_tokens": 0,
                   "total_tokens": usage_total},
            thinking=collected_thinking,
        )

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        """Convenience: one-shot system+user completion."""
        result = self.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return result.content

    @property
    def context_window(self) -> int:
        return 1_000_000  # DeepSeek V4: 1M tokens


# ══════════════════════════════════════════════════════════════════════════════
# Mock provider — deterministic fallback when the API is unreachable (offline demo)
# ══════════════════════════════════════════════════════════════════════════════


class MockProvider(DeepSeekProvider):
    """Deterministic rule-based provider for offline demos/tests.

    Returns keyword-templated answers; emits a JSON tool call for the first
    tool matching a keyword in the user message. Never touches the network.
    """

    name = "mock"

    def __init__(self, **kwargs):
        IPP.__init__(self)
        self.model = "mock"
        self.api_key = "mock"
        self.base_url = ""
        self.max_retries = 0
        self._client = None

    def chat(self, messages, tools=None, temperature=0.3, max_tokens=4096, stream=False) -> LLMResult:
        text = ""
        for m in reversed(messages):
            if m.get("role") in ("user", "tool"):
                text = m.get("content", "")
                break
        if text.startswith("[MOCK-ANSWER]") or any(m.get("role") == "system" and "MOCK" in str(m.get("content", "")) for m in messages):
            pass
        s = str(text).lower()
        # Tool-call simulation: ask for local graph / search / link ops
        if tools and ("graph" in s or "link" in s or "search" in s or "summar" in s):
            tool_name = None
            args = {}
            for t in tools:
                nm = t["function"]["name"]
                if nm == "get_local_graph" and "graph" in s:
                    tool_name, args = nm, {"node_id": "root", "depth": 3}
                    break
                if nm == "search_nodes" and "search" in s:
                    tool_name, args = nm, {"query": text, "k": 5}
                    break
                if nm == "link_nodes" and "link" in s:
                    tool_name, args = nm, {"source": "root", "target": "root", "relation": "related_to"}
                    break
            if tool_name:
                return LLMResult(
                    content="",
                    tool_calls=[{
                        "id": "mock-1",
                        "function": {"name": tool_name, "arguments": str(args)},
                    }],
                    usage={"total_tokens": 10},
                )
        reply = (
            f"[MOCK] Response to: {text[:200]}\n"
            "Offline mode: DeepSeek API not reachable. The agent loop and IPP "
            "pipeline executed successfully with deterministic output."
        )
        return LLMResult(content=reply, usage={"total_tokens": 10})

    def chat_stream(self, messages, tools=None, temperature=0.3, max_tokens=4096):
        """Mock streaming: yields the reply in word-sized chunks, then returns."""
        result = self.chat(messages, tools=tools, temperature=temperature,
                           max_tokens=max_tokens)
        if result.tool_calls:
            # simulate a single tool-call delta
            yield ("tool_delta", {"index": 0,
                                  "arguments": result.tool_calls[0]["function"]["arguments"]})
            return result
        words = (result.content or "").split(" ")
        for w in words:
            yield ("text", w + " ")
        return result
