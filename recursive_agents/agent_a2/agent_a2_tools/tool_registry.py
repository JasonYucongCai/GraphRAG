"""
agent_a1_tools.tool_registry — Per-Agent Tool Registry

Wraps all 50+ tools for agent_a1. Extends the runtime AgentToolkit
with the full copilot-level tool surface. This is what the LLM sees.

Categories:
  - agent_construction (8 tools) — build the next agent
  - file (6 tools) — read/write/replace/list files
  - search (4 tools) — grep, file search, references
  - terminal (6 tools) — PowerShell/shell interaction
  - memory (5 tools) — persistent memory operations
  - graph (8 tools) — knowledge graph queries
  - ipp (5 tools) — IPP construction/verification
  - llm (3 tools) — LLM backend interaction
  - evaluation (5 tools) — agent evaluation/testing
  - documentation (4 tools) — README/doc generation
  - log (5 tools) — logging and feedback
  - web (3 tools) — web search/fetch
  - system (5 tools) — system info/environment
  - powershell (3 tools) — agent process management
  - code (4 tools) — code generation/validation

Total: 70+ tools in 15 categories.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from .tool_base import BaseTool, ToolContext, ToolResult
from .agent_construction_tools import register_construction_tools
from .file_tools import register_file_tools
from .search_tools import register_search_tools
from .terminal_tools import register_terminal_tools
from .memory_tools import register_memory_tools
from .graph_tools import register_graph_tools
from .ipp_tools import register_ipp_tools
from .llm_tools import register_llm_tools
from .evaluation_tools import register_evaluation_tools
from .documentation_tools import register_documentation_tools
from .log_tools import register_log_tools
from .web_tools import register_web_tools
from .system_tools import register_system_tools
from .powershell_tools import register_powershell_tools
from .code_tools import register_code_tools


class AgentA1Toolkit:
    """Per-agent tool registry for agent_a1.

    Holds ALL 70+ tools in a unified registry. The tools node routes
    calls through this registry; the LLM sees tool definitions via
    `definitions()`.

    Usage:
        tk = AgentA1Toolkit(agent_id="agent_a1", ws_root=str(WS))
        tk.register_all()
        print(f"{tk.count()} tools available")
    """

    def __init__(self, agent_id: str = "agent_a1",
                 ws_root: str = "",
                 graph: Any = None, encoder: Any = None,
                 llm: Any = None):
        self.agent_id = agent_id
        self.ws_root = ws_root
        self.graph = graph
        self.encoder = encoder
        self.llm = llm
        self.tools: dict[str, BaseTool] = {}
        self.constructed: dict[str, Any] = {}
        self.chain: list[str] = []
        self._category_counts: dict[str, int] = {}

    # ── Registration ────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        self.tools[tool.tool_name] = tool
        cat = tool.category
        self._category_counts[cat] = self._category_counts.get(cat, 0) + 1

    def register_many(self, tools: list[BaseTool]) -> None:
        for t in tools:
            self.register(t)

    def register_all(self) -> None:
        """Register ALL 70+ tools from all category modules."""
        register_construction_tools(self)
        register_file_tools(self)
        register_search_tools(self)
        register_terminal_tools(self)
        register_memory_tools(self)
        register_graph_tools(self)
        register_ipp_tools(self)
        register_llm_tools(self)
        register_evaluation_tools(self)
        register_documentation_tools(self)
        register_log_tools(self)
        register_web_tools(self)
        register_system_tools(self)
        register_powershell_tools(self)
        register_code_tools(self)

    # ── Lookup ──────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)

    def count(self) -> int:
        return len(self.tools)

    def names(self) -> list[str]:
        return sorted(self.tools)

    def definitions(self) -> list[dict]:
        return [t.definition() for t in self.tools.values()]

    # ── Execution ───────────────────────────────────────────────────

    def execute(self, name: str, args: dict,
                ctx: Optional[ToolContext] = None) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult.fail(f"Unknown tool: {name!r}",
                                   error_type="unknown_tool")
        ctx = ctx or ToolContext(workspace_root=self.ws_root,
                                agent=self)
        return tool._run(args or {}, ctx)

    # ── Categories ──────────────────────────────────────────────────

    @property
    def categories(self) -> dict[str, int]:
        return dict(self._category_counts)

    @property
    def total_tools(self) -> int:
        return self.count()

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "total_tools": self.count(),
            "categories": self.categories,
            "tool_names": self.names(),
            "chain": list(self.chain),
            "constructed": sorted(self.constructed),
        }
