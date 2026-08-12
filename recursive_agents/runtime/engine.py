"""
recursive_agents.runtime.engine — the RecursiveAgentEngine.

The agentic loop of every recursive agent (a1, a2, a3, …). Reuses the
shared AgentEngine (general_tools.engine) for the LLM function-calling
loop and the observable trace; the tool dispatch goes through the SHARED
tools node (general_tools) — one execution plane, one audit trail. The
engine is the LOOP; the agent-construction capability lives in the
agent's TOOLS node (agent_plan / agent_generate / agent_create /
agent_evaluate / agent_test / agent_improve / agent_deploy /
agent_status), which carries the shared AgentCompiler bound by Γ.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from graph_agent import AgentEngine
from general_tools.encoder import EncoderLayer
from general_tools.graph import KnowledgeGraph

import time

# ── the tool surface every recursive agent exposes (its ACL) ────────────────
RECURSIVE_TOOL_NAMES: list[str] = [
    # graph reads
    "get_local_graph", "search_nodes", "read_node", "validate_graph",
    "summarize_local",
    # core codex
    "read_file", "grep_search", "current_time",
    "memory_read", "memory_write", "web_search",
    # database reads + light mutations (notes stay the source of truth)
    "list_projects", "project_info", "register_node", "link_nodes",
    "append_vcl",
]

DEFAULT_SYSTEM_PROMPT = (
    "You are a recursive agent in a self-adaptive chain. Ground your task, "
    "use your tools through the shared tools node, and when asked, construct "
    "the next recursive agent and improve it with feedback.")


class RecursiveAgentEngine(AgentEngine):
    """The engine of one recursive agent (level L). The agent's tools are
    its OWN toolkit (recursive_agents.runtime.toolkit.AgentToolkit) —
    including the REAL agent-construction tools with which it generates
    the next agent."""

    def __init__(self, graph: KnowledgeGraph, encoder: EncoderLayer,
                 llm: Any = None, llm_node: Any = None,
                 model: Optional[str] = None,
                 agent_id: str = "agent_a1", level: int = 1,
                 toolkit: Any = None,
                 system_prompt_text: Optional[str] = None,
                 tool_names: Optional[list[str]] = None,
                 store: Any = None):
        # Auto-load system_prompt.md from the agent's folder if not provided
        if system_prompt_text is None:
            prompt_path = (Path(__file__).resolve().parents[1] / agent_id
                           / "system_prompt.md")
            if prompt_path.exists():
                system_prompt_text = prompt_path.read_text(encoding="utf-8")
            else:
                system_prompt_text = DEFAULT_SYSTEM_PROMPT

        super().__init__(
            graph=graph, encoder=encoder, llm=llm, model=model,
            system_prompt=system_prompt_text,
            tool_names=tool_names or RECURSIVE_TOOL_NAMES,
            store=store,
        )
        self.name = agent_id
        self.agent_id = agent_id
        self.level = level
        self.toolkit = toolkit              # the agent's OWN tool registry
        self.node = None                    # the engine IPP node
        self._tools_node = None
        self._ipp_context = None

    # ── grounding (same contract as the codex engines) ────────────────────
    def ground(self, task: str, node_id: Any = None) -> str:
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
        for chunk, sim in self.encoder.search(task, k=4,
                                              node_filter=resolved):
            evidence.append(f"[chunk {chunk.chunk_id} sim={sim:.3f}] "
                            f"{chunk.text[:150]}")
        head = (f"{task}\n\nWORKING MEMORY — local graph of "
                f"{node.entryname} ({resolved}):\n" if node else
                f"{task}\n\nWORKING MEMORY — local graph of {resolved}:\n")
        body = local.verbalize(max_nodes=40, max_edges=50) if local \
            else "(empty)"
        return (head + body + "\n\nENCODER EVIDENCE:\n"
                + ("\n".join(evidence) if evidence else "(none)"))

    # ── TOOL ROUTING — override parent so the agent's OWN toolkit is
    #    visible to the LLM and dispatched correctly ─────────────────────
    # Priority tools the LLM sees in early rounds (construction + essentials).
    # In later rounds the full surface opens up so the LLM can review files.
    _PRIORITY_TOOLS = {
        "agent_plan", "agent_generate", "agent_create", "agent_evaluate",
        "agent_test", "agent_improve", "agent_deploy", "agent_status",
        "check_tool_count", "check_recursive_capability",
        "evaluate_engine_comprehensiveness", "ipp_verify", "ipp_audit",
        "read_file", "read_docs", "collect_feedback", "read_feedback",
        "read_log", "write_log", "write_feedback",
    }

    def _tool_definitions(self, round_index: int = 1) -> list[dict]:
        """Return tool definitions from BOTH the agent's own toolkit AND
        the shared tools node. In early rounds only priority tools are
        sent; after round 5 the full surface opens up."""
        own_defs = []
        if self.toolkit is not None:
            try:
                all_defs = self.toolkit.definitions()
            except Exception:
                all_defs = []
            # Early rounds: only priority tools to keep the LLM focused
            if round_index <= 4:
                own_defs = [d for d in all_defs
                            if d.get("function", {}).get("name", "")
                            in self._PRIORITY_TOOLS]
            else:
                own_defs = all_defs

        # Only add shared tools that are relevant
        shared_defs = super()._tool_definitions(round_index)
        # Filter shared tools to only include our priority set in early rounds
        if round_index <= 4:
            shared_defs = [d for d in shared_defs
                          if d.get("function", {}).get("name", "")
                          in self._PRIORITY_TOOLS]

        # Deduplicate by name; own toolkit wins for agent_* tools
        seen = set()
        merged = []
        for d in own_defs:
            name = d.get("function", {}).get("name", "")
            if name:
                seen.add(name)
            merged.append(d)
        for d in shared_defs:
            name = d.get("function", {}).get("name", "")
            if name and name not in seen:
                merged.append(d)
        return merged

    def _dispatch_tool(self, name: str, args: dict, ctx: Any) -> str:
        """Route the tool call: if the agent's own toolkit has this tool,
        execute it through the toolkit; otherwise fall through to the
        shared tools node (parent dispatch)."""
        if self.toolkit is not None and name in self.toolkit.tools:
            try:
                tk_ctx = type("ToolContext", (), {
                    "workspace_root": self.toolkit.ws_root,
                    "agent": self.toolkit,
                    "agent_name": self.agent_id,
                    "session_id": ctx.session_id if hasattr(ctx, "session_id") else "",
                })()
                result = self.toolkit.tools[name]._run(args or {}, tk_ctx)
                return str(result.content) if result.ok else (
                    f"[{name} ERROR] {result.error or 'unknown'}\n{result.content}")
            except Exception as exc:
                return f"[{name} EXCEPTION] {type(exc).__name__}: {exc}"
        # Fall through to shared tools node (parent's dispatch)
        return super()._dispatch_tool(name, args, ctx)
