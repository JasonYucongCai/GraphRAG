"""
LLMs.IPP_object — the IPP Objects (Ω_k) of the LLM node.

Each channel's handler H_k is bound by the Constructor Γ to the live
provider instance (from GraphContext.bindings["provider"]). Handlers only
see the envelope payload; all guardrails live in the Executor.

Axioms: O1 input conformance, O2 output conformance (LLMResult/str/dict),
O3 state preservation, O4 recall, O5 cross-channel state isolation.
"""
from __future__ import annotations

from typing import Any


def _normalize_chat(payload: Any) -> tuple[list, dict]:
    """Accept a bare message list or {messages, tools?, temperature?, ...}."""
    if isinstance(payload, dict):
        messages = payload.get("messages", [])
        kwargs = {k: v for k, v in payload.items()
                  if k not in ("messages",) and v is not None}
        return messages, kwargs
    return payload, {}


def make_chat_handler(bindings: dict):
    """H_chat — DeepSeek Chat Completions (function calling)."""
    provider = bindings["provider"]

    def handler(payload: Any, context: dict) -> dict:
        messages, kwargs = _normalize_chat(payload)
        result = provider.chat(messages, **kwargs)
        return {
            "content": result.content,
            "tool_calls": result.tool_calls,
            "usage": result.usage,
            "model": getattr(provider, "model", "?"),
        }

    return handler


def make_complete_handler(bindings: dict):
    """H_complete — single-shot system+user completion → text."""
    provider = bindings["provider"]

    def handler(payload: Any, context: dict) -> str:
        if isinstance(payload, str):
            return provider.complete("", payload)
        return provider.complete(
            payload.get("system", ""),
            payload.get("user", ""),
            temperature=payload.get("temperature", 0.2),
        )

    return handler


def make_chat_stream_handler(bindings: dict):
    """H_chat_stream — streaming events + accumulated LLMResult."""
    provider = bindings["provider"]

    def handler(payload: Any, context: dict) -> dict:
        messages, kwargs = _normalize_chat(payload)
        events = []
        result = None
        # chat_stream is a generator function that RETURNS the accumulated
        # LLMResult via PEP 380 (StopIteration.value)
        gen = provider.chat_stream(messages, **kwargs)
        while True:
            try:
                kind, data = next(gen)
                events.append((kind, data))
            except StopIteration as stop:
                result = stop.value
                break
        return {
            "events": events,
            "result": ({
                "content": result.content,
                "tool_calls": result.tool_calls,
                "usage": result.usage,
                "thinking": getattr(result, "thinking", None),
            } if result is not None else None),
        }

    return handler
