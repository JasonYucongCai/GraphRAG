"""
tools.api — the SHARED tool suite for all agents (IPP).

This is the single public interface for the tool layer. It composes:

  • the ORIGINAL codex 19-tool suite   (tools/codex_tools.py — copied verbatim)
  • the graph tools                    (tools/graph_tools — local graphs, encoder,
                                       node detail, validate, summarize)
  • the database mutations             (database/database_tool — add/edit/delete
                                       nodes & edges, references, VCL, sync)

All of them are exposed through ONE dispatch layer so the three agents
(codex_growth, codex_RAG, codex_normal) share the same ToolRegistry while each
chooses which tools it actually sends to the LLM.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("tools.api")

# ── the original codex 19-tool suite (flat functions) ────────────────────────
from tools.codex_tools import (  # noqa: F401
    TOOLS as CODEX_TOOLS,
    tool_shell_command, tool_read_file, tool_write_file,
    tool_list_directory, tool_search_files, tool_grep_search,
    tool_apply_patch, tool_view_image, tool_current_time,
    tool_plan, tool_request_user_input,
    tool_spawn_agent, tool_wait_agent, tool_list_agents, tool_cancel_agent,
    tool_send_notification, tool_memory_read, tool_memory_write,
    tool_web_search,
)

# ── graph tools + database mutations (IPP BaseTool classes) ──────────────────
from tools.IPP import ToolRegistry, ToolResult, ToolContext  # noqa: F401
from tools.graph_tools import ensure_tools as _ensure_graph_tools
from database.database_tool import ensure_database_tools as _ensure_db_tools
from tools.checks import ensure_check_tools as _ensure_check_tools

# re-export the mutation classes for direct use
from database.database_tool import (  # noqa: F401
    RegisterNodeTool, UpdateNodeTool, DeleteNodeTool,
    LinkNodesTool, UnlinkTool, InferEdgesTool, ProbeGapTool,
    AddReferenceTool, AppendVCLTool, SyncProjectTool,
)
# re-export the audit classes
from tools.checks import (  # noqa: F401
    ReviewTopThreatsTool, StandardCheckTool, AdvancedCheckTool,
)


# ══════════════════════════════════════════════════════════════════════════════
# Unified definitions + dispatch
# ══════════════════════════════════════════════════════════════════════════════

def ensure_tools() -> None:
    """Register every shared tool into the ToolRegistry (idempotent)."""
    _ensure_graph_tools()
    _ensure_db_tools()
    _ensure_check_tools()


def all_definitions(round_index: int = 1) -> list[dict]:
    """All tool JSON-Schemas for the LLM (deduped: IPP BaseTools win)."""
    ensure_tools()
    registry = {t.tool_name: t.definition() for t in ToolRegistry.all()}
    flat = {t["function"]["name"]: t for t in CODEX_TOOLS}
    chosen = {}
    for n, d in registry.items():
        if round_index < 2 and ToolRegistry.get(n).deferred:
            continue
        chosen[n] = d
    for n, d in flat.items():
        chosen.setdefault(n, d)
    return list(chosen.values())


def definitions_for(names: Optional[list[str]] = None, round_index: int = 1) -> list[dict]:
    """Tool schemas restricted to `names` (agent-tailored tool sets)."""
    ensure_tools()
    registry = {t.tool_name: t.definition() for t in ToolRegistry.all()}
    flat = {t["function"]["name"]: t for t in CODEX_TOOLS}
    chosen = {}
    if names:
        for n in names:
            if n in registry:
                if round_index < 2 and ToolRegistry.get(n).deferred:
                    continue
                chosen[n] = registry[n]
            elif n in flat:
                chosen[n] = flat[n]
    else:
        for n, d in registry.items():
            if round_index < 2 and ToolRegistry.get(n).deferred:
                continue
            chosen[n] = d
        for n, d in flat.items():
            chosen.setdefault(n, d)
    return list(chosen.values())


def execute_tool(name: str, args: dict, ctx: Optional[ToolContext] = None,
                 model_id: Optional[str] = None) -> str:
    """Dispatch a tool call: IPP BaseTools first, then the flat codex suite."""
    ensure_tools()
    tool = ToolRegistry.get(name, model_id)
    if tool is not None:
        result = ToolRegistry.execute(name, args, ctx, model_id)
        return str(result)
    flat = _FLAT_MAP.get(name)
    if flat is not None:
        try:
            return str(flat(**args))
        except TypeError as exc:
            return f"[ERROR] bad arguments for {name}: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"[ERROR] {name} failed: {exc}"
    return f"[ERROR] Unknown tool: {name!r}"


_FLAT_MAP = {
    "shell_command": tool_shell_command,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "list_directory": tool_list_directory,
    "search_files": tool_search_files,
    "grep_search": tool_grep_search,
    "apply_patch": tool_apply_patch,
    "view_image": tool_view_image,
    "current_time": tool_current_time,
    "plan": tool_plan,
    "request_user_input": tool_request_user_input,
    "spawn_agent": tool_spawn_agent,
    "wait_agent": tool_wait_agent,
    "list_agents": tool_list_agents,
    "cancel_agent": tool_cancel_agent,
    "send_notification": tool_send_notification,
    "memory_read": tool_memory_read,
    "memory_write": tool_memory_write,
    "web_search": tool_web_search,
}

TOOL_MAP = {**{t["function"]["name"]: t for t in CODEX_TOOLS}, **_FLAT_MAP}
TOOLS = all_definitions
