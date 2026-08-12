"""
swarm.live_handler — the live SSE streaming handler bound into per-agent
engine nodes (NOT part of the many_agents IPP node).

This handler is bound into each agent's engine ``chat_stream`` channel
so the portal's mini agent boxes update live. It runs the agent's
``engine.chat_stream`` generator inside the IPP guardrail envelope and
pushes every observable event to the swarm bus via ``context["on_event"]``.
"""
from __future__ import annotations


def make_live_chat_stream_handler(bindings: dict):
    engine = bindings["engine"]
    agent_id = bindings.get("agent_id", getattr(engine, "name", "agent"))

    def handler(payload, context: dict) -> dict:
        if isinstance(payload, dict):
            task = payload.get("task", "")
            node_id = payload.get("node_id")
        else:
            task, node_id = payload, None
        on_event = (context or {}).get("on_event")
        events: list[dict] = []
        answer_parts: list[str] = []
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
