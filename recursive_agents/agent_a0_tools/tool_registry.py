# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/tool_registry.py — ToolRegistry

Central registry for all tools in the system. Tools register themselves
at import time (side-effect pattern, same as Copilot's allTools.ts).

Features:
  - Tool registration by name
  - Deferred vs immediate tool routing
  - Model-specific tool overrides
  - Tool set grouping
  - Dynamic tool discovery
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .tool_base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger("codex.tools.registry")


class ToolRegistry:
    """Central registry for all tools.

    Usage:
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        tool = registry.get("read_file")
        result = await tool.invoke(args, context)

    Tools are registered once at startup. The registry determines
    which tools to send to the LLM based on the current round
    (deferred tools go on the 2nd request).
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._tools_by_ref: dict[str, BaseTool] = {}
        self._model_specific_tools: dict[str, dict[str, BaseTool]] = {}
        self._tool_sets: dict[str, list[str]] = {}
        self._deferred_tools: set[str] = set()
        self._immediate_tools: set[str] = set()

    # ── Registration ─────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a tool by its tool_name."""
        name = tool.tool_name
        if name in self._tools:
            logger.warning(f"Tool {name!r} already registered, overwriting")
        self._tools[name] = tool
        if tool.tool_reference_name:
            self._tools_by_ref[tool.tool_reference_name] = tool
        if tool.deferred:
            self._deferred_tools.add(name)
        else:
            self._immediate_tools.add(name)
        logger.debug(f"Registered tool: {name!r} (deferred={tool.deferred})")

    def register_many(self, tools: list[BaseTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def register_model_specific(
        self, name: str, model_id: str, tool: BaseTool
    ) -> None:
        """Register a model-specific variant of a tool."""
        if model_id not in self._model_specific_tools:
            self._model_specific_tools[model_id] = {}
        self._model_specific_tools[model_id][name] = tool
        logger.debug(f"Registered model-specific tool: {name!r} for {model_id}")

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        tool = self._tools.pop(name, None)
        if tool and tool.tool_reference_name:
            self._tools_by_ref.pop(tool.tool_reference_name, None)
        self._deferred_tools.discard(name)
        self._immediate_tools.discard(name)

    def add_to_set(self, set_name: str, tool_names: list[str]) -> None:
        """Group tools into a named set (for UI / organization)."""
        self._tool_sets[set_name] = tool_names

    # ── Lookup ───────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by its primary name."""
        return self._tools.get(name)

    def get_by_ref(self, ref_name: str) -> Optional[BaseTool]:
        """Get a tool by its reference name (alias)."""
        return self._tools_by_ref.get(ref_name)

    def get_for_model(self, name: str, model_id: str) -> Optional[BaseTool]:
        """Get a tool, preferring model-specific variant if available."""
        model_tools = self._model_specific_tools.get(model_id, {})
        return model_tools.get(name) or self._tools.get(name)

    def list_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def list_immediate(self) -> list[str]:
        """Return tool names sent on the first request."""
        return list(self._immediate_tools)

    def list_deferred(self) -> list[str]:
        """Return tool names sent on the second request."""
        return list(self._deferred_tools)

    # ── Definition building ──────────────────────────────────────────

    def get_tools_for_round(
        self, round_number: int, model_id: str = ""
    ) -> list[dict[str, Any]]:
        """Get OpenAI-format tool definitions for the given round.

        Round 1: only immediate tools (saves tokens).
        Round 2+: all tools including deferred.
        """
        if round_number <= 1:
            names = self._immediate_tools
        else:
            names = set(self._tools.keys())

        definitions = []
        for name in names:
            tool = self.get_for_model(name, model_id)
            if tool:
                definitions.append(tool.get_openai_tool_def(model_id))
        return definitions

    def get_all_definitions(self, model_id: str = "") -> list[dict[str, Any]]:
        """Get all tool definitions regardless of deferral."""
        definitions = []
        for name in self._tools:
            tool = self.get_for_model(name, model_id)
            if tool:
                definitions.append(tool.get_openai_tool_def(model_id))
        return definitions

    def get_definitions_by_names(
        self, names: list[str], model_id: str = ""
    ) -> list[dict[str, Any]]:
        """Get definitions for specific tool names."""
        definitions = []
        for name in names:
            tool = self.get_for_model(name, model_id)
            if tool:
                definitions.append(tool.get_openai_tool_def(model_id))
        return definitions

    # ── Tool set queries ─────────────────────────────────────────────

    def get_set_names(self) -> list[str]:
        """Return all tool set names."""
        return list(self._tool_sets.keys())

    def get_tools_in_set(self, set_name: str) -> list[BaseTool]:
        """Return all tools in a named set."""
        names = self._tool_sets.get(set_name, [])
        return [t for n in names if (t := self._tools.get(n))]

    # ── Execute dispatcher ───────────────────────────────────────────

    async def execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        context: ToolContext,
        model_id: str = "",
    ) -> ToolResult:
        """Full lifecycle execution of a tool.

        1. Look up the tool
        2. resolve_input — fix LLM parameter mistakes
        3. validate_input — JSON Schema validation
        4. prepare_invocation — user confirmation (if needed)
        5. invoke — execute

        Returns ToolResult with content or error.
        """
        tool = self.get_for_model(name, model_id)
        if tool is None:
            return ToolResult.fail(
                f"Unknown tool: {name!r}. Available: {', '.join(sorted(self._tools.keys()))}",
                error_type="unknown_tool",
            )

        try:
            # Step 1: Fix LLM mistakes
            args = await tool.resolve_input(args, context)
        except Exception as e:
            return ToolResult.fail(
                f"Error resolving input for {name}: {e}",
                error_type="resolve_input_error",
            )

        try:
            # Step 2: Validate
            errors = await tool.validate_input(args, context)
            if errors:
                return ToolResult.fail(
                    f"Invalid arguments for {name}: {'; '.join(errors)}\n"
                    f"Schema: {tool.tool_schema.get('properties', {})}\n"
                    f"Received: {args}",
                    error_type="validation_error",
                )
        except Exception as e:
            logger.warning(f"Validation error for {name}: {e}")

        try:
            # Step 3: Prepare
            prep = await tool.prepare_invocation(args, context)
            # (approval handling is done by the engine, not here)
        except Exception as e:
            return ToolResult.fail(
                f"Error preparing {name}: {e}",
                error_type="prepare_error",
            )

        try:
            # Step 4: Invoke
            result = await tool.invoke(args, context)
            return result
        except Exception as e:
            logger.exception(f"Tool {name} failed")
            return ToolResult.fail(
                f"Tool {name} failed: {e}",
                error_type="invoke_error",
            )

    # ── Queries ──────────────────────────────────────────────────────

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def immediate_count(self) -> int:
        return len(self._immediate_tools)

    @property
    def deferred_count(self) -> int:
        return len(self._deferred_tools)

    def get_summary(self) -> dict[str, Any]:
        """Return a summary of the registry state."""
        return {
            "total_tools": self.tool_count,
            "immediate": self.immediate_count,
            "deferred": self.deferred_count,
            "tools": [
                {
                    "name": t.tool_name,
                    "display": t.display_name,
                    "deferred": t.deferred,
                    "type": t.__class__.__name__,
                }
                for t in self._tools.values()
            ],
            "tool_sets": {
                name: len(names)
                for name, names in self._tool_sets.items()
            },
        }

    def clear(self) -> None:
        """Remove all registered tools."""
        self._tools.clear()
        self._tools_by_ref.clear()
        self._model_specific_tools.clear()
        self._tool_sets.clear()
        self._deferred_tools.clear()
        self._immediate_tools.clear()


# ── Global singleton ─────────────────────────────────────────────────

_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global ToolRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def reset_tool_registry() -> None:
    """Reset the global registry (for testing)."""
    global _global_registry
    if _global_registry:
        _global_registry.clear()
    _global_registry = None
