"""
agent_a1_tools.tool_base — Sync tool base classes

Sync port of assets/copilot_agent_tools/tool_base.py for agent_a1.

Every tool follows the four-phase lifecycle:
  1. resolve_input  — fix LLM parameter errors before validation
  2. validate_input  — JSON Schema validation
  3. prepare_invocation — user confirmation for dangerous ops
  4. invoke          — execute the tool (REAL work)

Tool categories:
  - BaseTool      — general-purpose tool
  - ReadOnlyTool  — guaranteed no side effects
  - EditTool      — modifies filesystem (requires confirmation)
  - ExecuteTool   — runs code/shell commands (requires confirmation)
  - WebTool       — makes network requests
  - MemoryTool    — reads/writes persistent memory
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("agent_a1.tools")


# ── Data types ──────────────────────────────────────────────────────

@dataclass
class ToolContext:
    """Context passed to every tool invocation."""
    workspace_root: str = ""
    session_id: str = ""
    request_id: str = ""
    agent_name: str = "agent_a1"
    agent: Any = None
    file_service: Any = None
    search_service: Any = None
    shell_service: Any = None
    memory_service: Any = None
    allowed_paths: list[str] = field(default_factory=list)
    working_directory: str = ""
    token_budget: int = 0
    tokens_used: int = 0
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def is_cancelled(self) -> bool:
        return self.cancelled


@dataclass
class ToolResult:
    """Structured result from a tool invocation."""
    ok: bool = True
    content: str = ""
    error: Optional[str] = None
    error_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def success(content: str = "", **meta) -> "ToolResult":
        meta.pop("ok", None)
        return ToolResult(True, content, None, "", dict(meta))

    @staticmethod
    def fail(message: str, error_type: str = "", **meta) -> "ToolResult":
        meta.pop("ok", None)
        return ToolResult(False, "", message, error_type, dict(meta))

    def to_dict(self) -> dict:
        d = {"ok": self.ok, "content": self.content,
             "error": self.error, "error_type": self.error_type}
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# ── Base Tool ───────────────────────────────────────────────────────

class BaseTool(ABC):
    """Abstract base for all agent_a1 tools.

    Subclasses must define:
      - tool_name: str       — unique identifier (e.g. "read_file")
      - tool_schema: dict    — JSON Schema for the LLM
      - description: str     — human-readable description
      - invoke(args, ctx)    — the actual work
    Optionally override:
      - resolve_input(args, ctx) — fix LLM errors
      - validate_input(args, ctx) — custom validation
      - prepare_invocation(args, ctx) — confirmation logic
    """

    tool_name: str = "unnamed"
    tool_schema: dict = {"type": "object", "properties": {}}
    category: str = "general"
    description: str = ""
    display_name: str = ""
    deferred: bool = False
    requires_confirmation: bool = False

    def definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description or self.tool_name,
                "parameters": self.tool_schema,
            },
        }

    def resolve_input(self, args: dict, ctx: ToolContext) -> dict:
        """Fix LLM parameter errors before validation. Override as needed."""
        return args

    def validate_input(self, args: dict, ctx: ToolContext) -> Optional[str]:
        """Return error message if invalid, None if valid."""
        required = self.tool_schema.get("required", [])
        for key in required:
            if key not in args or args[key] is None or args[key] == "":
                return f"Missing required parameter: {key!r}"
        return None

    def prepare_invocation(self, args: dict, ctx: ToolContext) -> Optional[str]:
        """Return reason to block, or None to proceed."""
        return None

    def _run(self, args: dict, ctx: ToolContext) -> ToolResult:
        """Full lifecycle: resolve → validate → prepare → invoke."""
        try:
            args = self.resolve_input(args, ctx)
            error = self.validate_input(args, ctx)
            if error:
                return ToolResult.fail(error, error_type="validation_error")
            block = self.prepare_invocation(args, ctx)
            if block:
                return ToolResult.fail(block, error_type="blocked")
            return self.invoke(args, ctx)
        except Exception as exc:
            logger.error(f"Tool {self.tool_name} failed: {exc}")
            return ToolResult.fail(f"{type(exc).__name__}: {exc}",
                                   error_type="tool_error")

    @abstractmethod
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        """Execute the tool. MUST be overridden."""
        ...


class ReadOnlyTool(BaseTool):
    """Tool with no side effects — safe for any mode."""
    pass


class EditTool(BaseTool):
    """Tool that modifies the filesystem — requires confirmation."""
    requires_confirmation: bool = True


class ExecuteTool(BaseTool):
    """Tool that runs code/shell commands — requires confirmation."""
    requires_confirmation: bool = True


class WebTool(BaseTool):
    """Tool that makes network requests."""
    pass


class MemoryTool(BaseTool):
    """Tool that reads/writes persistent memory."""
    pass
