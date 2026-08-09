"""
recursive_agent_module._ctor — IPP node constructor (Γ ⊩ IPP.json × 𝒢).

Usage (in server.py startup):
    from recursive_agents.recursive_agent_module._ctor import construct_ra_node
    ra_node = construct_ra_node(lock, graph, encoder, provider)

Then API routes call:
    ra_node.invoke("chain", {})
    ra_node.invoke("instruct", {"agent_id": "agent_a1", "task": "..."})
"""
from __future__ import annotations

import json, logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("recursive_agent_module")

_ra_node: Any = None


def construct_ra_node(lock, graph=None, encoder=None, provider=None) -> Any:
    """Construct the recursive agent IPP node through Γ.

    Returns the constructed IPPNode. The node is a singleton — subsequent
    calls return the same instance.
    """
    global _ra_node
    if _ra_node is not None:
        return _ra_node

    from IPP.IPP_constructor import IPPConstructor
    from IPP.IPP_registry import GraphContext
    from recursive_agents.recursive_agent_module.IPP_object import bind

    # Bind shared resources
    bind(lock, graph=graph, encoder=encoder, provider=provider)

    # Load F-file
    f_path = Path(__file__).resolve().parent / "IPP.json"
    f_doc = json.loads(f_path.read_text(encoding="utf-8"))

    # Construct
    ctx = GraphContext()
    from recursive_agents.recursive_agent_module.IPP_executor import RecursiveAgentExecutor
    channel_names = [c["channel_id"] for c in f_doc.get("channels", [])]
    gamma = IPPConstructor(
        ctx,
        executor_classes={ch: RecursiveAgentExecutor for ch in channel_names},
    )
    node = gamma.construct_file(str(f_path), ctx)
    gamma.recall_scope(node)
    ctx.register_node(node)

    _ra_node = node
    logger.info("recursive agent IPP node constructed: %s (%d channels)",
                node.node_id, len(node.channels))
    return node


def ra_node() -> Any:
    """Return the singleton IPP node (must call construct_ra_node first)."""
    if _ra_node is None:
        raise RuntimeError("recursive agent module not constructed — call construct_ra_node() first")
    return _ra_node
