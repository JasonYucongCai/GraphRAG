"""
agent_a1_tools.llm_tools — LLM backend interaction (3 tools)

llm_chat, llm_check, llm_provider_info
"""
from __future__ import annotations
import json
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class LLMChatTool(ReadOnlyTool):
    tool_name = "llm_chat"
    category = "llm"
    description = "Make a direct LLM call (for quick queries, not the main agent loop)."
    tool_schema = {
        "type": "object", "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "description": "The prompt to send."},
            "model": {"type": "string", "description": "Model name (optional)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        prompt = args.get("prompt", "")
        tk = ctx.agent
        if tk and tk.llm:
            try:
                response = tk.llm.chat([{"role": "user", "content": prompt}])
                return ToolResult.success(
                    str(response)[:2000],
                    prompt_len=len(prompt))
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success(
            "(LLM not available — offline mode)",
            prompt_len=len(prompt))


class LLMCheckTool(ReadOnlyTool):
    tool_name = "llm_check"
    category = "llm"
    description = "Check if the LLM backend is reachable."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if tk and tk.llm:
            try:
                ok = tk.llm.ping()
                return ToolResult.success(
                    f"LLM backend: {'reachable' if ok else 'unreachable'}",
                    reachable=ok)
            except Exception as e:
                return ToolResult.success(f"LLM check failed: {e}", reachable=False)
        return ToolResult.success("LLM backend: not configured (offline mode)",
                                  reachable=False)


class LLMProviderInfoTool(ReadOnlyTool):
    tool_name = "llm_provider_info"
    category = "llm"
    description = "Get information about the current LLM provider."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        tk = ctx.agent
        if tk and tk.llm:
            try:
                info = {
                    "provider": type(tk.llm).__name__,
                    "model": getattr(tk.llm, 'model', 'unknown'),
                }
                return ToolResult.success(
                    json.dumps(info, ensure_ascii=False, indent=2),
                    **info)
            except Exception:
                pass
        return ToolResult.success("LLM provider: not available")


def register_llm_tools(toolkit) -> None:
    toolkit.register_many([
        LLMChatTool(), LLMCheckTool(), LLMProviderInfoTool(),
    ])
