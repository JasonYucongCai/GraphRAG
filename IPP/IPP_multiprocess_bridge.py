"""
IPP.IPP_multiprocess_bridge — internal API for cross-process communication.

This Flask blueprint is registered ONLY on the Control Center process
(port 8000).  It exposes the unified /api/internal/invoke endpoint that
child processes (Multi Agent on 8001, Recursive Agent on 8002) call to
access shared resources (graph, encoder, database, codex tools) that
live in the Control Center.

Every call flows through the same IPP guardrail envelope as a local call,
so audit trails remain consistent across processes.

Protocol
--------
POST /api/internal/invoke
Body: {node_key, channel, payload}

  node_key   "self"      → tools_node's channel (graph, encoder, codex, …)
             "database"  → database_node's channel (project, nodes, edges, …)
  channel    the target channel id
  payload    the dict to pass to the channel's handler

Returns {ok, content, error, metadata} — identical to a local invoke().
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger("IPP.multiprocess_bridge")

bridge = Blueprint("ipp_bridge", __name__)


@bridge.post("/api/internal/invoke")
def internal_invoke():
    """Universal cross-process invoke: reconstruct the call against the
    Control Center's real singletons and return the result."""
    body = request.get_json(force=True, silent=True) or {}
    node_key = body.get("node_key", "")
    channel = body.get("channel", "")
    payload = body.get("payload", {}) or {}

    if not node_key or not channel:
        return jsonify({"ok": False, "error": "bad_request",
                        "content": "node_key + channel required"}), 400

    try:
        out = _dispatch(node_key, channel, payload)
        if not isinstance(out, dict):
            out = {"ok": True, "content": str(out), "error": None,
                   "metadata": {}}
        return jsonify(out)
    except Exception as exc:  # noqa: BLE001
        logger.exception("internal invoke failed: %s/%s", node_key, channel)
        return jsonify({"ok": False, "error": type(exc).__name__,
                        "content": f"[ERROR] {exc}", "metadata": {}}), 500


def _dispatch(node_key: str, channel: str, payload: dict) -> dict:
    """Reconstruct the target call on the Control Center side."""
    if node_key == "self":
        from general_tools.construct import tools_node
        return tools_node().executors[channel].invoke(payload).payload
    if node_key == "database":
        from database.construct import database_node
        return database_node().invoke(channel, payload).payload
    if node_key == "social_activity":
        return {"ok": False, "error": "bad_target",
                "content": "social_activity cannot be remote — it runs "
                           "in the Multi Agent process"}
    return {"ok": False, "error": "bad_target",
            "content": f"unknown node_key {node_key!r}"}
