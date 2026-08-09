"""
tools.construct — the Constructor (Γ) of the tools node + the shared-process
bridge.

Γ ⊩ tools/IPP.json × 𝒢 ↝ the SHARED runtime node with 26 channels
(invoke, list, describe, graph, encoder, build, check + the 19 codex
channels). The node is the SINGLE IPP surface of the shared tool layer:
the engine's dispatch (tools.api.execute_tool), the per-agent tools
nodes and the web server all invoke it through the guardrail envelopes,
and the tool DEFINITIONS the LLM sees are derived from the F-file
catalogs (tools/catalog.py) — there is no legacy BaseTool layer.

The shared bridge:

    bind_tools(graph, encoder, agents, social_node)  — (re)bind process-wide
    tools_node()                    — the singleton node (lazy construct)
    current_graph() / current_encoder() / current_agents()
    current_catalog()               — the F-file-derived tool catalog
    current_social_node()           — the platform's social node (routing)

One node per process: the server binds its graph/encoder at startup, the
platform registers the SAME node into its shared GraphContext 𝒢 (the
45th node), and the per-agent tools nodes (codex_* / ManyAgents) resolve
their invoke channel DOWNSTREAM to this node's invoke channel.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from IPP.IPP_constructor import IPPConstructor, IPPNode
from IPP.IPP_registry import GraphContext

logger = logging.getLogger("general_tools.construct")

_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"

# ── the shared bridge (process-wide) ───────────────────────────────────────
_lock = threading.RLock()
_GRAPH = None
_ENCODER = None
_AGENTS: dict = {}
_SOCIAL_NODE = None
_CATALOG: dict = {}
_NODE: Optional[IPPNode] = None
_CTX: Optional[GraphContext] = None


def bind_tools(graph=None, encoder=None, agents=None,
               social_node=None) -> None:
    """(Re)bind the process-wide KnowledgeGraph / EncoderLayer / agent
    lookup / social node the tools node operates on. Handlers resolve the
    bindings LIVE on every call, so rebinds (server startup,
    /api/graph/rebuild, platform assembly) are honored without
    re-construction (I1)."""
    global _GRAPH, _ENCODER, _AGENTS, _SOCIAL_NODE
    with _lock:
        if graph is not None:
            _GRAPH = graph
        if encoder is not None:
            _ENCODER = encoder
        if agents is not None:
            _AGENTS = dict(agents)
        if social_node is not None:
            _SOCIAL_NODE = social_node


def current_graph():
    return _GRAPH


def current_encoder():
    return _ENCODER


def current_agents() -> dict:
    return _AGENTS


def current_social_node():
    return _SOCIAL_NODE


def current_catalog() -> dict:
    return _CATALOG


def reset_tools_node() -> None:
    """Drop the singleton node (tests / full platform rebuilds)."""
    global _NODE, _CTX, _GRAPH, _ENCODER, _AGENTS, _SOCIAL_NODE, _CATALOG
    with _lock:
        _NODE, _CTX, _GRAPH, _ENCODER = None, None, None, None
        _AGENTS, _SOCIAL_NODE, _CATALOG = {}, None, {}


# ══════════════════════════════════════════════════════════════════════════
# Γ — construction (7-step protocol via IPP.IPP_constructor)
# ══════════════════════════════════════════════════════════════════════════
def create_tools_node(context: Optional[GraphContext] = None,
                      graph=None, encoder=None, agents=None,
                      social_node=None, register: bool = True) -> IPPNode:
    """Γ ⊩ tools/IPP.json × 𝒢 ↝ the tools IPP node (26 channels).

    Step 5/6: the tool CATALOG (the LLM definitions, derived from the
    F-file channel schemas) is built and bound here — one declarative
    source, no parallel tool layer.
    """
    from general_tools.IPP_executor import ToolsExecutor
    from general_tools.catalog import build_catalog

    ctx = context or GraphContext()
    if (graph is not None or encoder is not None or agents is not None
            or social_node is not None):
        bind_tools(graph=graph, encoder=encoder, agents=agents,
                   social_node=social_node)
    global _CATALOG
    with _lock:
        _CATALOG = build_catalog()
    ctx.bind("tools_graph", current_graph())
    ctx.bind("tools_encoder", current_encoder())
    ctx.bind("tools_agents", current_agents())
    ctx.bind("tools_social_node", current_social_node())
    ctx.bind("tools_catalog", _CATALOG)
    executor_channels = ("invoke", "list", "describe", "graph", "encoder",
                         "build", "check")
    gamma = IPPConstructor(ctx, executor_classes={
        ch: ToolsExecutor for ch in executor_channels})
    node = gamma.construct_file(_IPP_JSON, ctx)
    gamma.recall_scope(node)
    if register:
        ctx.register_node(node)
    return node


def tools_node(graph=None, encoder=None, agents=None,
               social_node=None) -> IPPNode:
    """The process-wide singleton tools node (lazy construction).

    First call constructs the node with the current shared bindings;
    later calls return the same instance — one node, one audit trail,
    registered by the platform into its shared GraphContext 𝒢.
    """
    global _NODE, _CTX
    with _lock:
        if (graph is not None or encoder is not None or agents is not None
                or social_node is not None):
            bind_tools(graph=graph, encoder=encoder, agents=agents,
                       social_node=social_node)
        if _NODE is None:
            _CTX = GraphContext()
            _NODE = create_tools_node(context=_CTX, register=True)
            logger.info("tools IPP node constructed: %s (%d channels, "
                        "%d catalog entries)", _NODE.node_id,
                        len(_NODE.channels), len(_CATALOG))
        return _NODE
