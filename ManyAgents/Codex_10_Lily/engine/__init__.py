"""
codex_normal.engine — the general-purpose engine package (IPP v0.2.8 node).

    engine = CodexNormalEngine(graph, encoder, llm=..., store=...)
    node   = construct_engine_node(engine)

Channels `ground` / `chat` / `chat_stream`; internal blocking edge
ground → chat composes the grounded general pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from tools.engine import AgentEngine
from tools.encoder import EncoderLayer
from tools.graph import KnowledgeGraph
from LLMs.deepseek import DeepSeekProvider
from tools.agent_specs import tool_set, chat_tool_set, system_prompt

AGENT_ID = "codex_normal"

_IPP_JSON = Path(__file__).resolve().parent / "ipp.json"


class CodexNormalEngine(AgentEngine):
    """The general-purpose engine — full tool suite, tailored prompt."""

    def __init__(self, graph: KnowledgeGraph, encoder: EncoderLayer,
                 llm: Optional[DeepSeekProvider] = None, store: Any = None,
                 model: Optional[str] = None, chat_mode: bool = False):
        names = chat_tool_set(AGENT_ID) if chat_mode else tool_set(AGENT_ID)
        super().__init__(
            graph=graph, encoder=encoder, llm=llm, model=model,
            system_prompt=system_prompt(AGENT_ID),
            tool_names=names, store=store,
        )
        self.name = AGENT_ID
        self.chat_mode = chat_mode
        self.node = None               # the IPP node (attached by create_agent)


def construct_engine_node(engine: CodexNormalEngine,
                          context=None, tool_names: Optional[list] = None,
                          register: bool = True):
    """Γ ⊩ codex_normal/engine/ipp.json × 𝒢 ↝ the engine IPP node."""
    from ipp.IPP_constructor import IPPConstructor
    from ipp.IPP_registry import GraphContext
    from codex_normal.engine.IPP_executor import AgentExecutor

    ctx = context or GraphContext()
    if "engine" not in ctx.bindings:
        ctx.bind("engine", engine)
    if tool_names is None:
        tool_names = tool_set(AGENT_ID)
    ctx.bind("tool_names", tool_names)
    gamma = IPPConstructor(ctx, executor_classes={
        "ground": AgentExecutor, "chat": AgentExecutor,
        "chat_stream": AgentExecutor})
    node = gamma.construct_file(_IPP_JSON, ctx)
    gamma.recall_scope(node)
    if register:
        ctx.register_node(node)
    return node
