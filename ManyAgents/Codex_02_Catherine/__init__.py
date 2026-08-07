"""
codex_normal — the general-purpose codex agent.

IPP v0.2.8: `create_agent()` constructs the engine node (engine/ipp.json),
the tools node (tools/ipp.json) and the LLM node (LLMs/ipp.json) through Γ,
attaching the engine node as `engine.node`. The returned engine stays fully
compatible with the AgentEngine surface (run_with_trace / chat_stream).
"""
from __future__ import annotations

from typing import Any, Optional

from codex_normal.engine import CodexNormalEngine, AGENT_ID
from LLMs.deepseek import DeepSeekProvider

__all__ = ["CodexNormalEngine", "create_agent", "AGENT_ID"]


def create_agent(graph, encoder, llm: Optional[DeepSeekProvider] = None,
                 store: Any = None, model: Optional[str] = None,
                 chat_mode: bool = False) -> CodexNormalEngine:
    """Build the engine + its IPP node and return the engine (node attached)."""
    from ipp.IPP_registry import GraphContext
    from codex_normal.engine import construct_engine_node
    from codex_normal.tools import construct_tools_node

    engine = CodexNormalEngine(graph, encoder, llm=llm, store=store,
                               model=model, chat_mode=chat_mode)

    ctx = GraphContext()
    if llm is not None:
        ctx.bind("provider", llm)
    else:
        from LLMs.IPP import _default_provider
        ctx.bind("provider", _default_provider())

    from LLMs.IPP import llm_node
    llm_node(context=ctx)
    tools_node = construct_tools_node(context=ctx)

    engine_node = construct_engine_node(engine, context=ctx)
    engine.node = engine_node
    engine._ipp_context = ctx
    engine._tools_node = tools_node
    return engine
