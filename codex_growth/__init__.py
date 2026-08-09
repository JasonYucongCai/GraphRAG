"""
codex_growth — the GROWTH agent (grows nodes & expands the network).

IPP v0.2.8: `create_agent()` constructs the engine node (engine/IPP.json),
the tools node (tools/IPP.json) and the LLM node (LLMs/IPP.json) through the
Constructor Γ, and attaches the engine node to the engine instance as
`engine.node`. The returned engine remains fully compatible with the
existing AgentEngine surface (run_with_trace / chat_stream / bind_node).
"""
from __future__ import annotations

from typing import Any, Optional

from codex_growth.engine import CodexGrowthEngine, AGENT_ID, _IPP_JSON
from LLMs.deepseek import DeepSeekProvider

__all__ = ["CodexGrowthEngine", "create_agent", "AGENT_ID"]


def create_agent(graph, encoder, llm: Optional[DeepSeekProvider] = None,
                 store: Any = None, model: Optional[str] = None,
                 chat_mode: bool = False) -> CodexGrowthEngine:
    """Build the engine + its IPP node (Γ ⊩ engine/IPP.json, tools/IPP.json,
    LLMs/IPP.json) and return the engine with `engine.node` attached."""
    from IPP.IPP_registry import GraphContext
    from codex_growth.engine import construct_engine_node
    from codex_growth.tools import construct_tools_node

    engine = CodexGrowthEngine(graph, encoder, llm=llm, store=store,
                               model=model, chat_mode=chat_mode)

    ctx = GraphContext()
    if llm is not None:
        ctx.bind("provider", llm)
    else:
        from LLMs.IPP import _default_provider
        ctx.bind("provider", _default_provider())

    # external partners: LLM node + this agent's tools node
    from LLMs.IPP import llm_node
    llm_node(context=ctx)
    tools_node = construct_tools_node(context=ctx)

    engine_node = construct_engine_node(engine, context=ctx)
    engine.node = engine_node
    engine._ipp_context = ctx
    engine._tools_node = tools_node
    return engine
