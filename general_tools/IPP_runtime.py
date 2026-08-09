"""
tools.IPP_runtime — the IPP v0.2.8 runtime bridge for the GraphRAG tool suite.

Public API:

    from general_tools.IPP_runtime import verify_node, tool_node, construct_from_file

    failures = verify_node(node)        # [] == ALL 17 OK
    tnode = tool_node("codex_growth")   # the tools node of an agent
    node   = construct_from_file("LLMs/IPP.json", bindings={...})

tools.IPP keeps the non-dispatch types (IPP, ToolResult, ToolContext,
ToolCallEvent); this module adds the v0.2.8 runtime (IPP/) on top.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from IPP.IPP_verify import verify_node  # noqa: F401  (the 17-invariant check)
from IPP.IPP_verify import verify_all  # noqa: F401
from IPP.IPP_constructor import IPPConstructor, IPPNode
from IPP.IPP_registry import GraphContext

logger = logging.getLogger("general_tools.IPP_runtime")


def construct_from_file(path, context: Optional[GraphContext] = None,
                        bindings: Optional[dict] = None,
                        executor_classes: Optional[dict] = None,
                        constructor: Optional[IPPConstructor] = None) -> IPPNode:
    """Γ ⊩ F(path) × 𝒢 ↝ IPPNode — generic file-driven construction."""
    ctx = context or GraphContext()
    for k, v in (bindings or {}).items():
        ctx.bind(k, v)
    gamma = constructor or IPPConstructor(ctx,
                                          executor_classes=executor_classes or {})
    node = gamma.construct_file(path, ctx)
    gamma.recall_scope(node)
    return node


def tool_node(agent_id: str = "codex_normal",
              context: Optional[GraphContext] = None,
              tool_names: Optional[list] = None):
    """Construct the tools node of an agent (codex_normal / codex_RAG /
    codex_growth) from its per-agent tools/IPP.json."""
    pkg = {"codex_normal": "codex_normal",
           "codex_RAG": "codex_RAG",
           "codex_growth": "codex_growth"}[agent_id]
    path = Path(__file__).resolve().parents[1] / pkg / "tools" / "IPP.json"
    if not path.exists():
        raise FileNotFoundError(f"no tools/IPP.json for {agent_id}: {path}")
    from general_tools.agent_specs import tool_set, chat_tool_set
    if tool_names is None:
        tool_names = tool_set(agent_id)
    bindings = {"tool_names": tool_names, "agent_id": agent_id}
    return construct_from_file(path, context=context, bindings=bindings)
