"""
codex_RAG — the RETRIEVAL / RAG agent (operates on & understands the network).

IPP v0.2.8: `create_agent()` constructs the engine node (engine/IPP.json),
the tools node (tools/IPP.json) and the LLM node (LLMs/IPP.json) through Γ,
attaching the engine node as `engine.node`.
"""
from __future__ import annotations

from typing import Any, Optional

from codex_RAG.engine import CodexRAGEngine, AGENT_ID

__all__ = ["CodexRAGEngine", "create_agent", "AGENT_ID"]


def create_agent(graph, encoder, llm_node: Any = None,
                 store: Any = None, model: Optional[str] = None,
                 chat_mode: bool = False) -> CodexRAGEngine:
    """Build the engine + its IPP node and return the engine (node attached).
    Uses the LLM IPP node (guardrail envelope + audit) — not raw provider."""
    from IPP.IPP_registry import GraphContext
    from codex_RAG.engine import construct_engine_node
    from codex_RAG.tools import construct_tools_node
    from LLMs import llm_node as _llm_node

    _llm = llm_node or _llm_node()
    engine = CodexRAGEngine(graph, encoder, llm_node=_llm, store=store,
                            model=model, chat_mode=chat_mode)

    ctx = GraphContext()
    from LLMs.IPP import _default_provider
    ctx.bind("provider", _default_provider())

    from LLMs.IPP import llm_node as _register_llm
    _register_llm(context=ctx)
    tools_node = construct_tools_node(context=ctx)

    engine_node = construct_engine_node(engine, context=ctx)
    engine.node = engine_node
    engine._ipp_context = ctx
    engine._tools_node = tools_node
    return engine
