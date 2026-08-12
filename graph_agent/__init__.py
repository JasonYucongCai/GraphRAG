"""
graph_agent — the graph-aware agent engine, a strict IPP v0.2.8 component.

The AgentEngine is the core agentic loop used by every agent in the platform
(codex_growth, codex_RAG, codex_normal, all 20 ManyAgents, all recursive
agents). It grounds tasks against a knowledge graph, calls the LLM through
the LLM IPP node (with full guardrail envelope + audit), dispatches tools
through the tools IPP node, and produces an observable trace.

    from graph_agent import AgentEngine

    engine = AgentEngine(graph, encoder, llm_node=llm_node)
    answer = engine.chat("What is the Hodge diamond of C3?")
    for event in engine.chat_stream(task):
        print(event.type, event.content)

The engine stores an LLM IPP node, NOT a raw DeepSeekProvider. Every LLM
call flows through the LLM node's guardrail envelope (ι→π→Ω→ι→ρ→τ*).
"""
from graph_agent.engine import AgentEngine  # noqa: F401
from graph_agent.types import ToolCallEvent, ToolContext  # noqa: F401

__all__ = ["AgentEngine", "ToolCallEvent", "ToolContext"]
