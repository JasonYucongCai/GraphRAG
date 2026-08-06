"""
codex_growth.engine.IPP_object — the IPP Objects (Ω_k) of the growth engine node.

Handlers are bound by Γ to the live CodexGrowthEngine instance
(GraphContext.bindings["engine"]). The `ground` channel produces the
grounded task; `chat` runs the raw agent loop; the internal edge
ground → chat composes them into the full pipeline.
"""
from __future__ import annotations

from typing import Any


def make_ground_handler(bindings: dict):
    """H_ground — materialize L3(node) + encoder evidence → grounded task."""
    engine = bindings["engine"]

    def handler(payload: dict, context: dict) -> str:
        task = payload.get("task", "")
        node_id = payload.get("node_id")
        return engine._ground(task, node_id)

    return handler


def make_chat_handler(bindings: dict):
    """H_chat — the raw agent loop (ungrounded; pipeline composes ground)."""
    engine = bindings["engine"]

    def handler(payload: Any, context: dict) -> dict:
        if isinstance(payload, str):
            task, node_id = payload, None
        else:
            task = payload.get("task", "")
            node_id = payload.get("node_id")
        answer, trace = engine.run_with_trace(task, node_id=node_id)
        return {
            "answer": answer,
            "trace": trace,
            "tokens": engine._session_tokens,
        }

    return handler


def make_chat_stream_handler(bindings: dict):
    """H_chat_stream — the observable agent loop as a collected event stream."""
    engine = bindings["engine"]

    def handler(payload: dict, context: dict) -> dict:
        task = payload.get("task", "")
        node_id = payload.get("node_id")
        events = []
        answer = ""
        for ev in engine.chat_stream(task, node_id=node_id):
            entry = {"type": ev.type}
            if ev.tool:
                entry["tool"] = ev.tool
            if ev.args is not None:
                entry["args"] = ev.args
            if ev.content is not None:
                entry["content"] = ev.content
            if ev.error is not None:
                entry["error"] = ev.error
            events.append(entry)
            if ev.type == "text":
                answer += ev.content or ""
        return {"events": events, "answer": answer.strip()}

    return handler
