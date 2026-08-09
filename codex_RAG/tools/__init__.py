"""
codex_RAG.tools — the RETRIEVAL / RAG agent's tool-suite IPP node.

    node = construct_tools_node(tool_names=None, context=None)

Channels: invoke / list / describe over the shared tools node, restricted
to the RAG tool set. Constructed by Γ from tools/IPP.json.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from IPP.IPP_constructor import IPPConstructor
from IPP.IPP_registry import GraphContext
from general_tools.agent_specs import tool_set
from general_tools.IPP_runtime import verify_node  # noqa: F401

AGENT_ID = "codex_RAG"
_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"


def construct_tools_node(tool_names: Optional[list] = None,
                         context: Optional[GraphContext] = None,
                         register: bool = True):
    """Γ ⊩ codex_RAG/tools/IPP.json × 𝒢 ↝ the tools IPP node."""
    from codex_RAG.tools.IPP_executor import ToolExecutor

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
