"""
swarm.IPP_object — the live streaming handler bound into every agent's
engine node (chat_stream channel).

The per-agent engine ``IPP.json`` files are finalized so that their
``chat_stream`` channel binds THIS handler instead of the plain
collecting handler. The handler runs the agent's own ``engine.chat_stream``
generator inside the IPP guardrail envelope and pushes every observable
event to the swarm bus *as it happens* via ``context["on_event"]`` — so
the portal's mini agent boxes update live, while the invocation still
flows through ι_pre → π → Ω → ι_post → ρ → τ* (Axiom X1).
"""
from __future__ import annotations

from typing import Any


def make_live_chat_stream_handler(bindings: dict):
    engine = bindings["engine"]
    agent_id = bindings.get("agent_id", getattr(engine, "name", "agent"))

    def handler(payload: Any, context: dict) -> dict:
        if isinstance(payload, dict):
            task = payload.get("task", "")
            node_id = payload.get("node_id")
        else:
            task, node_id = payload, None
        on_event = (context or {}).get("on_event")
        events: list[dict] = []
        answer_parts: list[str] = []
        # fresh session per task — each task is an independent turn
        engine.messages = []
        engine._session_tokens = 0
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
            if on_event is not None:
                on_event(agent_id, entry)
            if ev.type == "text":
                answer_parts.append(ev.content or "")
        return {"events": events, "answer": "".join(answer_parts).strip(),
                "tokens": engine._session_tokens}

    return handler
