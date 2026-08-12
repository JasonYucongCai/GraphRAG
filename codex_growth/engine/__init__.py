"""
codex_growth.engine — the GROWTH engine package (IPP v0.2.8 node).

The CodexGrowthEngine class (AgentEngine) plus the IPP node construction:

    engine = CodexGrowthEngine(graph, encoder, llm=..., store=...)
    node   = construct_engine_node(engine)   # Γ ⊩ engine/IPP.json × 𝒢

The node has channels `ground` / `chat` / `chat_stream` with an internal
blocking edge ground → chat: invoke("ground", {task, node_id}) runs the full
grounded agent pipeline and returns {answer, trace, tokens}.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from graph_agent import AgentEngine
from general_tools.encoder import EncoderLayer
from general_tools.graph import KnowledgeGraph
from general_tools.agent_specs import tool_set, chat_tool_set, system_prompt

AGENT_ID = "codex_growth"

_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"


class CodexGrowthEngine(AgentEngine):
    """The growth engine — bound to the network, growth-tailored prompt."""

    def __init__(self, graph: KnowledgeGraph, encoder: EncoderLayer,
                 llm: Any = None, llm_node: Any = None,
                 store: Any = None,
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

    def _ground(self, task: str, node_id: Any) -> str:
        anchor = node_id if node_id is not None else self.node_id
        if anchor is None:
            return task
        resolved = self.graph.resolve(anchor)
        if resolved is None:
            return task
        node = self.graph.get_node(resolved)
        try:
            local = self.graph.materialize_local(resolved, 3)
        except Exception:  # noqa: BLE001
            local = None
        evidence = []
        for chunk, sim in self.encoder.search(task, k=4, node_filter=resolved):
            evidence.append(f"[chunk {chunk.chunk_id} sim={sim:.3f}] {chunk.text[:150]}")
        head = f"{task}\n\nWORKING MEMORY — local graph of {node.entryname} ({resolved}):\n"
        body = local.verbalize(max_nodes=40, max_edges=50) if local else "(empty)"
        return (head + body + "\n\nENCODER EVIDENCE:\n"
                + ("\n".join(evidence) if evidence else "(none)"))

    def chat(self, task: str, node_id: Any = None, verbose: bool = True) -> str:
        answer, _ = self.run_with_trace(self._ground(task, node_id), node_id=node_id)
        return answer

    def chat_stream(self, task: str, node_id: Any = None):
        yield from super().chat_stream(self._ground(task, node_id), node_id=node_id)


def construct_engine_node(engine: CodexGrowthEngine,
                          context=None, tool_names: Optional[list] = None,
                          register: bool = True):
    """Γ ⊩ codex_growth/engine/IPP.json × 𝒢 ↝ the engine IPP node."""
    from IPP.IPP_constructor import IPPConstructor
    from IPP.IPP_registry import GraphContext
    from codex_growth.engine.IPP_executor import AgentExecutor

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
