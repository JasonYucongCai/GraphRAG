# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/__init__.py — Copilot-Style Tool System

Provides:
  - BaseTool, ReadOnlyTool, EditTool, ExecuteTool, WebTool, MemoryTool
  - ToolRegistry with deferred tool routing
  - ToolValidator with JSON Schema validation and recovery
  - ToolDeferralService for token-efficient tool loading
  - All individual tool implementations

Usage:
    from tools.copilot import ToolRegistry, get_tool_registry, BaseTool
    from tools.copilot import ReadFileTool, GrepSearchTool, ShellCommandTool
"""

from .tool_base import (
    BaseTool, ReadOnlyTool, EditTool, ExecuteTool, WebTool, MemoryTool,
    ToolContext, ToolResult, ToolCallEvent, PreparedInvocation,
)
from .tool_registry import ToolRegistry, get_tool_registry, reset_tool_registry
from .tool_validation import ToolValidator, get_validator
from .tool_deferral import ToolDeferralService, get_deferral_service, AgentMode, ToolCategory

# Tool implementations
from .read_file import ReadFileTool
from .write_file import WriteFileTool, CreateDirectoryTool
from .replace_string import ReplaceStringTool, MultiReplaceStringTool
from .search_tools import SearchFilesTool, GrepSearchTool, ListDirectoryTool
from .shell_tools import (
    ShellCommandTool, PlanTool, ManageTodoListTool, TaskCompleteTool,
)
from .sub_agent import (
    SearchSubagentTool, ExecutionSubagentTool,
    SpawnAgentTool, WaitAgentTool, ListAgentsTool, CancelAgentTool,
)
from .memory_tools import (
    MemoryReadTool, MemoryWriteTool,
    WebSearchTool, CurrentTimeTool, GetErrorsTool,
    ViewImageTool, RequestUserInputTool, SendNotificationTool,
)
