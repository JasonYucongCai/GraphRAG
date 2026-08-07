"""
codex_normal.engine.IPP_object — the IPP Objects (Ω_k) of the general engine node.

The base AgentEngine has no `_ground`; the ground handler implements the
depth-3 local-graph grounding inline (same contract as the growth/RAG
engines).
"""
from __future__ import annotations

from typing import Any


def _ground_impl(engine, task: str, node_id: Any) -> str:
    anchor = node_id if node_id is not None else engine.node_id
    if anchor is None:
        return task
    resolved = engine.graph.resolve(anchor)
    if resolved is None:
        return task
    node = engine.graph.get_node(resolved)
    try:
        local = engine.graph.materialize_local(resolved, 3)
    except Exception:  # noqa: BLE001
        local = None
    evidence = []
    for chunk, sim in engine.encoder.search(task, k=4, node_filter=resolved):
        evidence.append(f"[chunk {chunk.chunk_id} sim={sim:.3f}] {chunk.text[:150]}")
    head = f"{task}\n\nWORKING MEMORY — local graph of {node.entryname} ({resolved}):\n"
    body = local.verbalize(max_nodes=40, max_edges=50) if local else "(empty)"
    return (head + body + "\n\nENCODER EVIDENCE:\n"
            + ("\n".join(evidence) if evidence else "(none)"))


def make_ground_handler(bindings: dict):
    engine = bindings["engine"]

    def handler(payload: dict, context: dict) -> str:
        return _ground_impl(engine, payload.get("task", ""),
                            payload.get("node_id"))

    return handler


def make_chat_handler(bindings: dict):
    engine = bindings["engine"]

    def handler(payload: Any, context: dict) -> dict:
        if isinstance(payload, str):
            task, node_id = payload, None
        else:
            task = payload.get("task", "")
            node_id = payload.get("node_id")
        answer, trace = engine.run_with_trace(task, node_id=node_id)
        return {"answer": answer, "trace": trace,
                "tokens": engine._session_tokens}

    return handler


def make_chat_stream_handler(bindings: dict):
    engine = bindings["engine"]

    def handler(payload: dict, context: dict) -> dict:
        events, answer = [], ""
        for ev in engine.chat_stream(payload.get("task", ""),
                                     payload.get("node_id")):
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
