"""
codex_normal.tools.IPP_object — the IPP Objects (Ω_k) of the general tools node.
"""
from __future__ import annotations

from typing import Any, Optional

from general_tools.IPP import ToolContext


def make_invoke_handler(bindings: dict):
    tool_names = set(bindings.get("tool_names") or [])

    def handler(payload: dict, context: dict) -> dict:
        tool = payload.get("tool", "")
        args = payload.get("args", {}) or {}
        if tool not in tool_names:
            return {"content": f"tool {tool!r} not in this agent's tool set",
                    "ok": False, "error": "tool_not_allowed", "metadata": {}}
        # strict IPP: the agent tools node delegates to the SHARED tools
        # node (tools/IPP.json via Γ) — one execution plane, one audit
        # trail; the ACL (tool_names) stays enforced here.
        from general_tools.construct import tools_node
        out = tools_node().invoke(
            "invoke", {"tool": tool, "args": args,
                       "agent_id": bindings.get("agent_id", "")}).payload
        if not isinstance(out, dict):
            out = {"content": str(out), "ok": bool(out), "error": None,
                   "metadata": {}}
        return {"content": out.get("content", ""), "ok": out.get("ok", False),
                "error": out.get("error"), "metadata": out.get("metadata", {})}

    return handler


def make_list_handler(bindings: dict):
    tool_names = sorted(bindings.get("tool_names") or [])

    def handler(payload: Any, context: dict) -> list:
        return tool_names

    return handler


def make_describe_handler(bindings: dict):
    tool_names = set(bindings.get("tool_names") or [])

    def handler(payload: dict, context: dict) -> Optional[dict]:
        tool = payload.get("tool", "")
        if tool not in tool_names:
            return None
        # strict IPP: the definition comes from the shared tools node's
        # F-file catalog (list/describe channels)
        from general_tools.construct import tools_node
        out = tools_node().invoke("describe", {"tool": tool}).payload
        if not isinstance(out, dict) or not out.get("ok"):
            return None
        return out.get("definition")

    return handler
