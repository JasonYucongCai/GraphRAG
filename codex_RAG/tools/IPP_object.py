"""
codex_RAG.tools.IPP_object — the IPP Objects (Ω_k) of the RAG tools node.
"""
from __future__ import annotations

from typing import Any, Optional

from tools.IPP import ToolRegistry, ToolContext


def make_invoke_handler(bindings: dict):
    tool_names = set(bindings.get("tool_names") or ToolRegistry.names())

    def handler(payload: dict, context: dict) -> dict:
        tool = payload.get("tool", "")
        args = payload.get("args", {}) or {}
        if tool not in tool_names:
            return {"content": f"tool {tool!r} not in this agent's tool set",
                    "ok": False, "error": "tool_not_allowed", "metadata": {}}
        result = ToolRegistry.execute(tool, args, ToolContext())
        return {"content": result.content, "ok": result.ok,
                "error": result.error, "metadata": result.metadata}

    return handler


def make_list_handler(bindings: dict):
    tool_names = sorted(bindings.get("tool_names") or ToolRegistry.names())

    def handler(payload: Any, context: dict) -> list:
        return tool_names

    return handler


def make_describe_handler(bindings: dict):
    tool_names = set(bindings.get("tool_names") or ToolRegistry.names())

    def handler(payload: dict, context: dict) -> Optional[dict]:
        tool = payload.get("tool", "")
        if tool not in tool_names:
            return None
        tool_obj = ToolRegistry.get(tool)
        return tool_obj.definition() if tool_obj else None

    return handler
