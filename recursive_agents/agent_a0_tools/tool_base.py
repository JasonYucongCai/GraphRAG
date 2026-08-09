# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/tool_base.py — Python equivalent of Copilot's ICopilotTool<T> interface.

Provides the base class that all tools must extend, with the full lifecycle:
  resolve_input → validate → prepare_invocation → invoke

Architecture:
  BaseTool (ABC)
    ├── tool_name: str          — Unique tool identifier
    ├── tool_schema: dict       — JSON Schema definition for the LLM
    ├── deferred: bool          — Send on 2nd request to save tokens
    ├── resolve_input()         — Fix LLM parameter errors before validation
    ├── validate_input()        — JSON Schema validation (can override)
    ├── prepare_invocation()    — User confirmation for dangerous ops
    ├── invoke()                — Execute the tool (abstract)
    └── alternative_definition()— Per-model schema overrides
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("codex.tools")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    """Context passed to every tool invocation.

    Carries workspace info, session state, and references to services
    the tool might need — Copilot equivalent of the DI container.
    """
    workspace_root: str = ""
    session_id: str = ""
    request_id: str = ""
    agent_name: str = "codex"

    # Optional service references (set by the engine before tool execution)
    file_service: Any = None          # For file I/O abstraction
    search_service: Any = None        # For text/file search abstraction
    shell_service: Any = None         # For terminal/shell abstraction
    memory_service: Any = None        # For persistent memory
    notification_service: Any = None  # For push notifications
    mcp_registry: Any = None          # For MCP tool lookup
    allowed_paths: list[str] = field(default_factory=list)
    working_directory: str = ""

    # Token budget tracking
    token_budget: int = 0
    tokens_used: int = 0

    # Cancellation support
    cancelled: bool = False
    cancellation_callback: Optional[Callable[[], bool]] = None

    # Extra metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_cancelled(self) -> bool:
        if self.cancelled:
            return True
        if self.cancellation_callback:
            return self.cancellation_callback()
        return False


@dataclass
class ToolResult:
    """Structured result from a tool invocation.

    Mirrors Copilot's LanguageModelToolResult.
    """
    content: str = ""
    error: Optional[str] = None
    error_type: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, Any]] = field(default_factory=list)
    has_error: bool = False
    truncated: bool = False
    total_lines: int = 0
    lines_returned: int = 0

    def __str__(self) -> str:
        if self.has_error:
            return f"[ERROR] {self.error or 'Unknown error'}"
        suffix = ""
        if self.truncated:
            suffix = f"\n[... result truncated, showing {self.lines_returned} of {self.total_lines} ...]"
        return self.content + suffix

    @classmethod
    def ok(cls, content: str = "", **meta) -> "ToolResult":
        return cls(content=content, metadata=meta)

    @classmethod
    def fail(cls, error: str, error_type: str = "tool_error", **meta) -> "ToolResult":
        return cls(error=error, error_type=error_type, has_error=True, metadata=meta)


@dataclass
class ToolCallEvent:
    """Event emitted during tool execution for streaming/UI updates."""
    type: str                           # "tool_call" | "tool_result" | "approval" | "error"
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    error: Optional[str] = None
    approval_required: bool = False
    timestamp: float = 0.0
    tool_call_id: str = ""


@dataclass
class PreparedInvocation:
    """Result of prepare_invocation — tells the engine what to show the user."""
    confirmation_message: str = ""
    requires_approval: bool = False
    approval_prompt: str = ""
    invocation_message: str = ""


# ---------------------------------------------------------------------------
# BaseTool — the core abstraction
# ---------------------------------------------------------------------------

class BaseTool(ABC):
    """Python equivalent of Copilot's ICopilotTool<T>.

    Every tool in the system extends this class. The lifecycle is:

    1. resolve_input(raw_args, context)  → Fix common LLM mistakes
    2. validate_input(args, context)      → JSON Schema validation
    3. prepare_invocation(args, context)   → Show user what will happen
    4. invoke(args, context)              → Execute the tool

    Subclasses MUST set:
      - tool_name: str
      - tool_schema: dict (JSON Schema)

    Subclasses MUST implement:
      - invoke()

    Subclasses MAY override:
      - resolve_input()
      - prepare_invocation()
      - alternative_definition()
      - deferred (property)
    """

    # ── MUST be set by subclass ──────────────────────────────────────
    tool_name: str = ""
    tool_schema: dict = {}

    # ── MAY be overridden ────────────────────────────────────────────
    deferred: bool = False          # Send on 2nd request to save tokens
    runs_in_workspace: bool = True  # False for pure web tools
    can_request_approval: bool = False  # User can pre-approve
    tool_reference_name: str = ""   # Shorter alias for the LLM
    display_name: str = ""          # Human-readable name
    model_description: str = ""     # Description the LLM sees
    user_description: str = ""      # Human-readable tooltip
    tags: list[str] = field(default_factory=list)
    icon: str = ""                  # Emoji or codicon

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.tool_name:
            cls.tool_name = cls.__name__.removesuffix("Tool").lower()
        if not cls.display_name:
            cls.display_name = cls.tool_name.replace("_", " ").title()
        if not cls.tool_reference_name:
            cls.tool_reference_name = cls.tool_name

    # ── Lifecycle methods ────────────────────────────────────────────

    @abstractmethod
    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute the tool. Args have been validated and normalized.

        This is the main entry point — the only method subclasses MUST implement.
        """
        ...

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Fix common LLM parameter errors before validation.

        Override to:
        - Convert relative paths to absolute
        - Fix wrong parameter names (e.g., 'path' → 'filePath')
        - Set defaults for missing optional params
        - Coerce types (string "42" → int 42)

        Returns the corrected args dict.
        """
        return args

    async def prepare_invocation(
        self, args: dict[str, Any], context: ToolContext
    ) -> PreparedInvocation:
        """Return a PreparedInvocation to show the user before execution.

        Override for:
        - Destructive operations (file delete, shell rm)
        - External file access confirmation
        - Large operations (read 10000 files)

        Return PreparedInvocation(requires_approval=False) to skip.
        """
        return PreparedInvocation(
            invocation_message=f"Running {self.display_name}..."
        )

    async def validate_input(
        self, args: dict[str, Any], context: ToolContext
    ) -> list[str]:
        """Validate args against the tool's JSON Schema.

        Returns a list of error messages. Empty list = valid.
        """
        from .tool_validation import ToolValidator
        validator = ToolValidator()
        return validator.validate(args, self.tool_schema)

    def alternative_definition(self, model_id: str) -> Optional[dict]:
        """Return a different JSON Schema for specific models.

        Override when different models need different parameter formats.
        Returns None to use the default tool_schema.
        """
        return None

    # ── Helper methods ───────────────────────────────────────────────

    def get_definition(self, model_id: str = "") -> dict:
        """Get the tool definition for the given model.

        Returns the alternative definition if available, else the default.
        """
        alt = self.alternative_definition(model_id) if model_id else None
        schema = alt or self.tool_schema
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.model_description or schema.get("description", ""),
                "parameters": {
                    k: v for k, v in schema.items() if k != "description"
                },
            },
        }

    def get_openai_tool_def(self, model_id: str = "") -> dict:
        """Get the OpenAI-format tool definition."""
        return self.get_definition(model_id)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} tool_name={self.tool_name!r}>"


# ---------------------------------------------------------------------------
# Convenience base classes for common tool patterns
# ---------------------------------------------------------------------------

class ReadOnlyTool(BaseTool):
    """Tool that only reads data — never modifies files.

    These tools can always run without user confirmation.
    """
    runs_in_workspace: bool = True
    can_request_approval: bool = False

    async def prepare_invocation(
        self, args: dict[str, Any], context: ToolContext
    ) -> PreparedInvocation:
        return PreparedInvocation()


class EditTool(BaseTool):
    """Tool that modifies files — may require user confirmation.

    These tools should override prepare_invocation to show a diff or
    confirmation message before applying changes.
    """
    runs_in_workspace: bool = True
    can_request_approval: bool = True

    async def prepare_invocation(
        self, args: dict[str, Any], context: ToolContext
    ) -> PreparedInvocation:
        return PreparedInvocation(
            confirmation_message=f"Editing file: {args.get('filePath', args.get('path', 'unknown'))}",
            requires_approval=self.can_request_approval,
        )


class ExecuteTool(BaseTool):
    """Tool that runs commands or code — may need sandboxing."""
    runs_in_workspace: bool = True
    can_request_approval: bool = True
    timeout_seconds: int = 30

    async def prepare_invocation(
        self, args: dict[str, Any], context: ToolContext
    ) -> PreparedInvocation:
        cmd = args.get("command", args.get("query", ""))[:80]
        return PreparedInvocation(
            confirmation_message=f"Running: {cmd}",
            requires_approval=True,
            invocation_message=f"Executing: {cmd}...",
        )


class WebTool(BaseTool):
    """Tool that accesses the internet — may need network access."""
    runs_in_workspace: bool = False
    can_request_approval: bool = False
    tags: list[str] = field(default_factory=lambda: ["web"])

    async def prepare_invocation(
        self, args: dict[str, Any], context: ToolContext
    ) -> PreparedInvocation:
        return PreparedInvocation(
            invocation_message=f"Fetching: {args.get('query', args.get('url', ''))[:60]}..."
        )


class MemoryTool(BaseTool):
    """Tool for persistent memory operations — read/write to memory store."""
    runs_in_workspace: bool = True
    can_request_approval: bool = False
    tags: list[str] = field(default_factory=lambda: ["memory"])

    async def prepare_invocation(
        self, args: dict[str, Any], context: ToolContext
    ) -> PreparedInvocation:
        return PreparedInvocation()
