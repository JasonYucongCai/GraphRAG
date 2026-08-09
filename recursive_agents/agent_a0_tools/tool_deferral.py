# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/tool_deferral.py — Tool Deferral Service

Copilot equivalent: toolDeferralService.ts

Manages which tools are sent to the LLM on which round to save tokens.
Immediate tools go on request 1; deferred tools on request 2+.

Strategy (from Copilot):
  - Read tools (read_file, list_directory, grep_search, file_search):
    ALWAYS immediate — the LLM needs these for every task.
  - Edit tools (replace_string, write_file, apply_patch):
    Immediate for Agent/Edit modes, deferred for Ask mode.
  - Sub-agent tools (execution_subagent, search_subagent):
    Always deferred — expensive, sent on 2nd request.
  - Web tools (fetch_webpage, github_repo):
    Always deferred — rarely needed.
  - VS Code tools (install_extension, run_vscode_command):
    Always deferred — niche use.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("codex.tools.deferral")


class ToolCategory(Enum):
    """Categories for tool grouping (matching Copilot's ToolCategory enum)."""
    CORE = "Core"
    FILE_READ = "File Read"
    FILE_WRITE = "File Write"
    SEARCH = "Search"
    SHELL = "Shell / Execute"
    SUB_AGENT = "Sub-Agent"
    WEB = "Web Interaction"
    JUPYTER = "Jupyter Notebook"
    MEMORY = "Memory"
    VSCODE = "VS Code Interaction"
    MCP = "MCP External"


# ── Deferral Rules ───────────────────────────────────────────────────

# Tools that are ALWAYS sent immediately (round 1)
ALWAYS_IMMEDIATE: set[str] = {
    "read_file",
    "list_directory",
    "search_files",
    "grep_search",
    "view_image",
    "get_errors",
    "current_time",
    "plan",
    "manage_todo_list",
    "task_complete",
    "memory_read",
    "memory_write",
    "request_user_input",
}

# Tools that are deferred (sent on round 2+)
ALWAYS_DEFERRED: set[str] = {
    "execution_subagent",
    "search_subagent",
    "explore_subagent",
    "fetch_webpage",
    "github_repo",
    "github_text_search",
    "install_extension",
    "run_vscode_command",
    "get_vscode_api",
    "create_new_workspace",
    "tool_search",
    "session_store_sql",
    "create_new_jupyter_notebook",
    "edit_notebook",
    "run_notebook_cell",
    "get_notebook_summary",
    "read_notebook_cell_output",
    "resolve_memory_file_uri",
}

# Tools that are immediate for Agent/Edit modes but deferred for Ask mode
EDIT_MODE_IMMEDIATE: set[str] = {
    "replace_string",
    "multi_replace_string",
    "apply_patch",
    "write_file",
    "create_file",
    "create_directory",
    "insert_edit",
}

# Shell tools are immediate for Agent mode only
AGENT_ONLY_IMMEDIATE: set[str] = {
    "shell_command",
    "run_in_terminal",
    "get_terminal_output",
    "send_to_terminal",
    "kill_terminal",
    "terminal_selection",
    "terminal_last_command",
    "create_and_run_task",
    "run_task",
    "get_task_output",
    "send_notification",
}


class AgentMode(Enum):
    """Chat modes matching Copilot's ChatModeKind."""
    ASK = "ask"
    EDIT = "edit"
    AGENT = "agent"
    PLAN = "plan"
    EXPLORE = "explore"
    CUSTOM = "custom"


class ToolDeferralService:
    """Manages which tools are sent on which round.

    Usage:
        svc = ToolDeferralService()
        tools = svc.get_tools_for_round(1, AgentMode.AGENT)
        # → immediate tools only
        tools = svc.get_tools_for_round(2, AgentMode.AGENT)
        # → all tools
    """

    def __init__(self):
        self._overrides: dict[str, bool] = {}  # tool_name → force_immediate

    def force_immediate(self, tool_name: str) -> None:
        """Force a tool to be sent immediately (override deferral)."""
        self._overrides[tool_name] = True
        logger.debug(f"Forced immediate: {tool_name!r}")

    def force_deferred(self, tool_name: str) -> None:
        """Force a tool to be deferred (override immediate)."""
        self._overrides[tool_name] = False
        logger.debug(f"Forced deferred: {tool_name!r}")

    def is_immediate(self, tool_name: str, mode: AgentMode) -> bool:
        """Check if a tool should be sent immediately for the given mode.

        Decision priority:
          1. Explicit override (force_immediate/force_deferred)
          2. ALWAYS_IMMEDIATE set
          3. ALWAYS_DEFERRED set
          4. Mode-dependent rules
        """
        # Override check
        if tool_name in self._overrides:
            return self._overrides[tool_name]

        # Always immediate
        if tool_name in ALWAYS_IMMEDIATE:
            return True

        # Always deferred
        if tool_name in ALWAYS_DEFERRED:
            return False

        # Edit tools: immediate for Agent and Edit modes
        if tool_name in EDIT_MODE_IMMEDIATE:
            return mode in (AgentMode.AGENT, AgentMode.EDIT)

        # Shell tools: immediate for Agent mode only
        if tool_name in AGENT_ONLY_IMMEDIATE:
            return mode == AgentMode.AGENT

        # Default: deferred
        return False

    def is_deferred(self, tool_name: str, mode: AgentMode) -> bool:
        """Check if a tool should be deferred."""
        return not self.is_immediate(tool_name, mode)

    def get_tool_names_for_round(
        self,
        round_number: int,
        mode: AgentMode,
        all_tool_names: list[str],
    ) -> list[str]:
        """Get tool names to send on the given round."""
        if round_number <= 1:
            return [
                name for name in all_tool_names
                if self.is_immediate(name, mode)
            ]
        return list(all_tool_names)

    def get_deferred_tool_names(
        self, mode: AgentMode, all_tool_names: list[str]
    ) -> list[str]:
        """Get only the deferred tool names."""
        return [
            name for name in all_tool_names
            if self.is_deferred(name, mode)
        ]

    def reset(self) -> None:
        """Clear all overrides."""
        self._overrides.clear()

    def get_summary(self, mode: AgentMode, tool_names: list[str]) -> dict:
        """Get a summary of deferral decisions."""
        immediate = [n for n in tool_names if self.is_immediate(n, mode)]
        deferred = [n for n in tool_names if self.is_deferred(n, mode)]
        return {
            "mode": mode.value,
            "total": len(tool_names),
            "immediate": len(immediate),
            "immediate_names": sorted(immediate),
            "deferred": len(deferred),
            "deferred_names": sorted(deferred),
        }


# ── Singleton ────────────────────────────────────────────────────────

_global_deferral: Optional[ToolDeferralService] = None


def get_deferral_service() -> ToolDeferralService:
    global _global_deferral
    if _global_deferral is None:
        _global_deferral = ToolDeferralService()
    return _global_deferral
