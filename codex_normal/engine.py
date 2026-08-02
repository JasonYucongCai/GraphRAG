"""
codex_normal — the general-purpose codex agent (IPP).

The usual codex agent that can DO things: read/write files, run shell
commands, search code, plan, spawn sub-agents, memory, notifications and web
search. This is the agent you chat with for general tasks (see chat.py for the
Gradio interface).

Tailored tool set + system prompt (see tools/agent_specs.py). Shares the
common tools/ and LLMs/ with codex_growth and codex_RAG.
"""
from __future__ import annotations

from typing import Any, Optional

from tools.engine import AgentEngine
from tools.encoder import EncoderLayer
from tools.graph import KnowledgeGraph
from LLMs.deepseek import DeepSeekProvider
from tools.agent_specs import tool_set, chat_tool_set, system_prompt

AGENT_ID = "codex_normal"


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


def create_agent(graph: KnowledgeGraph, encoder: EncoderLayer,
                 llm: Optional[DeepSeekProvider] = None, store: Any = None,
                 model: Optional[str] = None, chat_mode: bool = False) -> CodexNormalEngine:
    return CodexNormalEngine(graph, encoder, llm=llm, store=store, model=model,
                             chat_mode=chat_mode)
