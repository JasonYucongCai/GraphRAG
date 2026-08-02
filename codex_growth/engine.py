"""
codex_growth — the GROWTH agent (IPP).

Improves node .md notes by considering new analysis & information (web search,
file read) and EXPANDS the network — adding new edges, updating and adding new
nodes — using the mutation tools in database/database_tool.

Tailored tool set + system prompt (see tools/agent_specs.py). Shares the
common tools/ and LLMs/ with codex_RAG and codex_normal.
"""
from __future__ import annotations

from typing import Any, Optional

from tools.engine import AgentEngine
from tools.encoder import EncoderLayer
from tools.graph import KnowledgeGraph
from LLMs.deepseek import DeepSeekProvider
from tools.agent_specs import tool_set, chat_tool_set, system_prompt

AGENT_ID = "codex_growth"


class CodexGrowthEngine(AgentEngine):
    """The growth engine — bound to the network, growth-tailored prompt."""

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


def create_agent(graph: KnowledgeGraph, encoder: EncoderLayer,
                 llm: Optional[DeepSeekProvider] = None, store: Any = None,
                 model: Optional[str] = None, chat_mode: bool = False) -> CodexGrowthEngine:
    return CodexGrowthEngine(graph, encoder, llm=llm, store=store, model=model,
                             chat_mode=chat_mode)
