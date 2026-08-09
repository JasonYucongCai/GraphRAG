# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""tools/copilot/register.py — Mega-Registry: ALL tools in one unified registry.

Registration order matters: Copilot tools take priority, then Codex fallbacks
for tools without Copilot equivalents, then Grok-specific tools.
No overwrite warnings — we check before registering.
"""
from __future__ import annotations
import logging
logger = logging.getLogger("codex.tools.register")
_REGISTERED = False


def _register_if_missing(reg, tool) -> bool:
    """Register a tool only if its name is not already taken. Returns True if registered."""
    if tool.tool_name in reg._tools:
        return False
    reg.register(tool)
    return True


def _register_many_if_missing(reg, tools: list) -> int:
    """Register multiple tools, skipping those already registered. Returns count added."""
    count = 0
    for tool in tools:
        if _register_if_missing(reg, tool):
            count += 1
    return count


def register_all_tools() -> int:
    global _REGISTERED
    if _REGISTERED:
        from .tool_registry import get_tool_registry
        return get_tool_registry().tool_count

    from .tool_registry import get_tool_registry
    reg = get_tool_registry()

    # ═══════════════════════════════════════════════════════════════
    # PHASE 1 — Copilot tools (register first — they're the best)
    # ═══════════════════════════════════════════════════════════════

    # 1a. Copilot Read tools
    from .read_file import ReadFileTool
    from .search_tools import ListDirectoryTool
    from .memory_tools import ViewImageTool
    _register_many_if_missing(reg, [ReadFileTool(), ListDirectoryTool(), ViewImageTool()])

    # 1b. Copilot Search tools
    from .search_tools import SearchFilesTool, GrepSearchTool
    from .vscode_tools import SearchWorkspaceSymbolsTool, FindTestFilesTool
    from .core_tools import GetChangedFilesTool, ReadProjectStructureTool
    _register_many_if_missing(reg, [
        SearchFilesTool(), GrepSearchTool(),
        SearchWorkspaceSymbolsTool(), FindTestFilesTool(),
        GetChangedFilesTool(), ReadProjectStructureTool(),
    ])

    # 1c. Copilot Edit tools
    from .write_file import WriteFileTool, CreateDirectoryTool
    from .replace_string import ReplaceStringTool, MultiReplaceStringTool
    from .core_tools import EditFileCoreTool
    _register_many_if_missing(reg, [
        WriteFileTool(), CreateDirectoryTool(),
        ReplaceStringTool(), MultiReplaceStringTool(),
        EditFileCoreTool(),
    ])

    # 1d. Copilot Execute tools
    from .shell_tools import ShellCommandTool
    from .sub_agent import ExecutionSubagentTool
    from .terminal_tools import RunInTerminalTool
    _register_many_if_missing(reg, [ShellCommandTool(), ExecutionSubagentTool(), RunInTerminalTool()])

    # 1e. Copilot Plan tools
    from .shell_tools import PlanTool, ManageTodoListTool, TaskCompleteTool
    from .memory_tools import RequestUserInputTool
    _register_many_if_missing(reg, [PlanTool(), ManageTodoListTool(), TaskCompleteTool(), RequestUserInputTool()])

    # 1f. Copilot Sub-Agent tools
    from .sub_agent import SearchSubagentTool, SpawnAgentTool, WaitAgentTool, ListAgentsTool, CancelAgentTool
    from .core_tools import ExploreSubagentTool
    from .vscode_tools import SwitchAgentTool
    _register_many_if_missing(reg, [
        SearchSubagentTool(), ExploreSubagentTool(),
        SpawnAgentTool(), WaitAgentTool(), ListAgentsTool(), CancelAgentTool(),
        SwitchAgentTool(),
    ])

    # 1g. Copilot Memory tools
    from .memory_tools import MemoryReadTool, MemoryWriteTool
    from .vscode_tools import ResolveMemoryFileUriTool, SessionStoreSqlTool
    _register_many_if_missing(reg, [MemoryReadTool(), MemoryWriteTool(), ResolveMemoryFileUriTool(), SessionStoreSqlTool()])

    # 1h. Copilot Web tools
    from .memory_tools import WebSearchTool
    from .web_tools import FetchWebpageTool, GithubRepoTool, GithubTextSearchTool
    _register_many_if_missing(reg, [WebSearchTool(), FetchWebpageTool(), GithubRepoTool(), GithubTextSearchTool()])

    # 1i. Copilot Utility tools
    from .memory_tools import CurrentTimeTool, GetErrorsTool, SendNotificationTool
    from .web_tools import ToolSearchTool
    _register_many_if_missing(reg, [CurrentTimeTool(), GetErrorsTool(), SendNotificationTool(), ToolSearchTool()])

    # 1j. Copilot Jupyter tools
    from .notebook_tools import (
        CreateJupyterNotebookTool, EditNotebookTool, RunNotebookCellTool,
        GetNotebookSummaryTool, ReadNotebookCellOutputTool,
    )
    _register_many_if_missing(reg, [
        CreateJupyterNotebookTool(), EditNotebookTool(), RunNotebookCellTool(),
        GetNotebookSummaryTool(), ReadNotebookCellOutputTool(),
    ])

    # 1k. Copilot Terminal tools
    from .terminal_tools import (
        GetTerminalOutputTool, SendToTerminalTool, KillTerminalTool,
        TerminalSelectionTool, TerminalLastCommandTool,
        CreateAndRunTaskTool, GetTaskOutputTool,
    )
    _register_many_if_missing(reg, [
        GetTerminalOutputTool(), SendToTerminalTool(), KillTerminalTool(),
        TerminalSelectionTool(), TerminalLastCommandTool(),
        CreateAndRunTaskTool(), GetTaskOutputTool(),
    ])

    # 1l. Copilot VS Code tools
    from .vscode_tools import GetVSCodeAPITool, InstallExtensionTool, RunVSCodeCommandTool, CreateNewWorkspaceTool
    _register_many_if_missing(reg, [GetVSCodeAPITool(), InstallExtensionTool(), RunVSCodeCommandTool(), CreateNewWorkspaceTool()])

    # 1m. Copilot Core tools
    from .core_tools import (
        AskQuestionsTool, ConfirmationTool, ReviewPlanTool,
        SetArtifactRulesTool, SetArtifactsTool, TestFailureTool,
    )
    _register_many_if_missing(reg, [
        AskQuestionsTool(), ConfirmationTool(), ReviewPlanTool(),
        SetArtifactRulesTool(), SetArtifactsTool(), TestFailureTool(),
    ])

    copilot_count = reg.tool_count
    logger.info(f"Copilot: {copilot_count} tools registered")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2 — Codex fallback tools (only if no Copilot equivalent)
    # ═══════════════════════════════════════════════════════════════
    from tools.codex.tool_classes import CODEX_TOOL_CLASSES
    codex_added = 0
    for cls in CODEX_TOOL_CLASSES:
        tool = cls()
        if _register_if_missing(reg, tool):
            codex_added += 1
    if codex_added > 0:
        logger.info(f"Codex: {codex_added} fallback tools (no Copilot equivalent)")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 3 — Grok-specific tools (SpaceXAI grok-build port)
    # ═══════════════════════════════════════════════════════════════
    try:
        from tools.grok.register import register_all_grok_tools
        grok_added = register_all_grok_tools()
        if grok_added:
            logger.info(f"Grok: {grok_added} tools registered")
    except ImportError:
        logger.debug("Grok tools not available")

    _REGISTERED = True
    total = reg.tool_count
    logger.info(f"MEGA-REGISTRY: {total} tools across Copilot + Codex + Grok")
    return total


def is_registered() -> bool:
    return _REGISTERED
