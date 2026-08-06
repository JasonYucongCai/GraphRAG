"""
codex_growth.tools — the GROWTH agent's tool-suite IPP node.

    node = construct_tools_node(tool_names=None, context=None)

Channels: invoke / list / describe over the shared ToolRegistry, restricted
to the growth tool set. Constructed by Γ from tools/ipp.json.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ipp.IPP_constructor import IPPConstructor
from ipp.IPP_registry import GraphContext
from tools.agent_specs import tool_set
from tools.IPP_runtime import verify_node  # noqa: F401  (re-export convenience)

AGENT_ID = "codex_growth"
_IPP_JSON = Path(__file__).resolve().parent / "ipp.json"


def construct_tools_node(tool_names: Optional[list] = None,
                         context: Optional[GraphContext] = None,
                         register: bool = True):
    """Γ ⊩ codex_growth/tools/ipp.json × 𝒢 ↝ the tools IPP node."""
    from codex_growth.tools.IPP_executor import ToolExecutor

    ctx = context or GraphContext()
    if tool_names is None:
        tool_names = tool_set(AGENT_ID)
    ctx.bind("tool_names", tool_names)
    ctx.bind("agent_id", AGENT_ID)
    gamma = IPPConstructor(ctx, executor_classes={
        "invoke": ToolExecutor, "list": ToolExecutor,
        "describe": ToolExecutor})
    node = gamma.construct_file(_IPP_JSON, ctx)
    gamma.recall_scope(node)
    if register:
        ctx.register_node(node)
    return node
