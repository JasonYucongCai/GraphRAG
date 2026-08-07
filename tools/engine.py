"""
tools.engine — the IPP agent engine (agentic loop).

A self-contained implementation of the Codex/Copilot-style agent loop:

    user message → prompt assembly → LLM call (DeepSeek) → tool execution
    (four-phase pipeline via ToolRegistry) → repeat → final answer

Key patterns retained from the reference architectures:
  • Event-driven chat_stream() yielding ToolCallEvents (observable trace)
  • MAX_TOOL_ROUNDS bound + context auto-compaction
  • Session-scoped approval cache
  • Tool results truncated for context efficiency
  • IPP composition: AgentEngine ∘ Tool ∘ KnowledgeGraph ∘ Encoder

The engine is bound to a graph + encoder so that graph tools operate on the
network. It is itself an IPP: (task) → Φ → (answer).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Generator, Optional

from tools.config import Config
from tools.encoder import EncoderLayer
from tools.graph import KnowledgeGraph
from tools.IPP import IPP, ToolCallEvent, ToolContext, ToolRegistry
from LLMs.deepseek import DeepSeekProvider

logger = logging.getLogger("tools.engine")

DEFAULT_SYSTEM_PROMPT = """You are a knowledge-graph agent operating inside a Graph Knowledge Network.

## Your environment
- You work on NODES of a knowledge graph. Each task is anchored on one node.
- You NEVER see the whole graph. You materialize and operate on the LOCAL GRAPH
  of the anchor node: its depth-3 connected neighborhood (get_local_graph).
- The network has an ENCODER layer: chunks of node content are embedded and
  searchable by vector similarity (search_nodes). Use it to pull in facts.
- Edges are typed and bidirectional-consistent. Growth ops (register_node,
  link_nodes, infer_edges, probe_gap) respect dedup and per-run limits.

## Operating procedure
1. Materialize the local graph of the anchor node (depth 3).
2. Vector-search the query over the encoder layer.
3. Reason over the local graph + retrieved chunks; use tools for further info.
4. If you discover a genuinely new, self-contained topic: register_node then
   link_nodes to its motivating nodes (dedup first).
5. When done, answer concisely. If the task was a growth task, run
   validate_graph to confirm consistency before finishing.

## Rules
- Prefer get_local_graph + search_nodes over reading whole documents.
- Do not invent edges; every link must be justified by evidence in context.
- Respect limits: ≤5 new nodes per run; dedup before creating.
- Use validate_graph after any mutation."""


class AgentEngine(IPP):
    """The IPP agent engine bound to a graph network."""

    name = "agent"

    def __init__(
        self,
        graph: KnowledgeGraph,
        encoder: EncoderLayer,
        llm: Optional[DeepSeekProvider] = None,
        model: Optional[str] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        node_id: Any = None,
        tool_names: Optional[list] = None,
        store: Any = None,
    ):
        super().__init__()
        self.graph = graph
        self.encoder = encoder
        self.llm = llm or DeepSeekProvider(model=model)
        self.system_prompt = system_prompt
        self.node_id = node_id              # anchor node for this session
        self.tool_names = tool_names        # None = all shared tools
        self.store = store                  # NoteStore for database_tool
        self.messages: list[dict] = []
        self._session_approvals: dict = {}
        self._session_tokens: int = 0
        self._turn: Optional[dict] = None
        self.name = f"agent[{node_id}]" if node_id is not None else "agent"
        # True  → provider.chat_stream (HTTP streaming, per-token deltas)
        # False → provider.chat (single non-streaming completion) — the
        #         many-agent default (streaming serializes concurrent agents)
        self.llm_stream: bool = True
        self.run_limits = {
            "new_subjects": Config.MAX_NEW_SUBJECTS_PER_RUN,
            "new_refs_per_subject": Config.MAX_REFS_PER_SUBJECT_PER_RUN,
            "new_refs_total": Config.MAX_REFS_PER_RUN,
        }
        self._run_counts = {"new_subjects": 0, "new_refs": 0}

    # ── tool-layer integration (shared tools.api) ────────────────────────
    def _tool_definitions(self, round_index: int = 1) -> list[dict]:
        from tools.api import definitions_for
        return definitions_for(self.tool_names, round_index)

    def _dispatch_tool(self, name: str, args: dict, ctx: "ToolContext") -> str:
        from tools.api import execute_tool
        return execute_tool(name, args, ctx)

    # ── IPP: (task) → Φ → (answer) ───────────────────────────────────────
    def transform(self, inp: dict) -> str:
        task = inp.get("task", "")
        node_id = inp.get("node_id", self.node_id)
        return self.chat(task, node_id=node_id)

    def reset(self) -> None:
        self.messages.clear()
        self._session_tokens = 0
        self._turn = None

    # ── Public ───────────────────────────────────────────────────────────
    def chat(self, task: str, node_id: Any = None, verbose: bool = True) -> str:
        """Run the loop, return the final answer text."""
        answer, _trace = self.run_with_trace(task, node_id=node_id)
        return answer

    def run_with_trace(self, task: str, node_id: Any = None,
                       ) -> tuple[str, list[dict]]:
        """
        Run the agentic loop and return (final_answer, trace).

        trace is an ordered list of every observable step:
          {type:'thinking', content}
          {type:'message', content}          — assistant text (pre/post tool)
          {type:'tool_call', tool, args}
          {type:'tool_result', tool, content}
          {type:'answer', content}           — the final answer
        """
        self.last_trace: list[dict] = []
        answer = ""
        for event in self.chat_stream(task, node_id=node_id):
            entry: dict = {"type": event.type}
            if event.tool:
                entry["tool"] = event.tool
            if event.args is not None:
                entry["args"] = event.args
            if event.content is not None:
                entry["content"] = event.content
            if event.error is not None:
                entry["error"] = event.error
            self.last_trace.append(entry)
            if event.type == "text":
                answer += event.content or ""
        return answer.strip(), self.last_trace

    def chat_stream(self, task: str, node_id: Any = None
                    ) -> Generator[ToolCallEvent, None, None]:
        """The agentic loop, yielding ToolCallEvents (observable trace).

        Event types: start, thinking, message, tool_call, tool_result,
        text (final answer), done, error.

        The loop FORCES a text answer once the tool budget is exhausted —
        the model can never loop on tools forever (that was the "truncated /
        empty answer" bug).
        """
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self._turn = {"turn_id": str(uuid.uuid4())[:8], "tools": [],
                      "tokens": 0, "started": time.time()}
        self.messages.append({"role": "user", "content": task})
        yield ToolCallEvent(type="start", content=f"turn {self._turn['turn_id']}")

        max_rounds = Config.MAX_TOOL_ROUNDS
        force_at = max(3, max_rounds - 2)   # force text from this round on

        for round_num in range(1, max_rounds + 1):
            self._maybe_compact()

            # ── tool budget exhausted → force a plain-text answer ────────
            forced = round_num >= force_at
            tools = None if forced else self._tool_definitions(round_num)
            if forced:
                nudge = ("[SYSTEM] You have used enough tool calls. Do NOT call "
                         "any more tools. Write your final answer now as plain "
                         "text, complete and detailed.")
                if not self.messages or self.messages[-1].get("content") != nudge:
                    self.messages.append({"role": "user", "content": nudge})

            try:
                content_delta = ""
                thinking_delta = ""
                result = None
                if getattr(self, "llm_stream", True):
                    # ── STREAMING LLM call: yields thinking/text deltas as
                    #    they arrive, so the UI renders progressively ────
                    gen = self.llm.chat_stream(self.messages, tools=tools,
                                               temperature=Config.TEMPERATURE)
                    try:
                        while True:
                            kind, data = next(gen)
                            if kind == "thinking":
                                thinking_delta += data
                                yield ToolCallEvent(type="thinking", content=data)
                            elif kind == "text":
                                content_delta += data
                                # stream assistant text progressively
                                yield ToolCallEvent(type="message_delta", content=data)
                            elif kind == "usage":
                                pass  # captured at end
                    except StopIteration as e:
                        result = e.value
                else:
                    # ── NON-STREAMING LLM call (many-agent default): one
                    #    completion; full thinking/message events follow ──
                    result = self.llm.chat(
                        self.messages, tools=tools,
                        temperature=Config.TEMPERATURE)
                    content_delta = result.content or ""
            except Exception as exc:  # noqa: BLE001
                logger.error("LLM call failed: %s", exc)
                yield ToolCallEvent(type="error", error=str(exc))
                return

            if result is None:
                yield ToolCallEvent(type="error", error="LLM returned nothing")
                return

            # a full 'message' event with the complete assistant text
            if content_delta:
                yield ToolCallEvent(type="message", content=content_delta)

            if result.usage:
                self._session_tokens += result.usage.get("total_tokens", 0)
                self._turn["tokens"] += result.usage.get("total_tokens", 0)

            # thinking (DeepSeek reasoning_content, when enabled) — full
            if result.thinking:
                yield ToolCallEvent(type="thinking", content=result.thinking)

            if not result.tool_calls:
                full = content_delta or result.content
                self.messages.append({"role": "assistant", "content": full})
                yield ToolCallEvent(type="text", content=full)
                yield ToolCallEvent(
                    type="done", rounds=round_num,
                    usage={"total": self._session_tokens},
                    content=full,
                )
                return

            # Record assistant tool-call message
            self.messages.append({
                "role": "assistant",
                "content": content_delta or result.content or "",
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["function"]["name"],
                                  "arguments": tc["function"]["arguments"]}}
                    for tc in result.tool_calls
                ],
            })

            for tc in result.tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                self._turn["tools"].append(name)
                yield ToolCallEvent(type="tool_call", tool=name, args=args,
                                    content=f"round {round_num}")

                ctx = self._tool_context(node_id)
                tool_result = self._dispatch_tool(name, args, ctx)
                display = str(tool_result)
                yield ToolCallEvent(type="tool_result", tool=name, content=display)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": display[:1200] + ("…[truncated]" if len(display) > 1200 else ""),
                })

        # exhausted every round — synthesize whatever assistant text we have
        reply = self.messages[-1].get("content", "") if self.messages else ""
        yield ToolCallEvent(type="text", content=reply or "[no answer produced]")
        yield ToolCallEvent(type="error", error="max tool rounds exceeded (forced answer)")

    # ── helpers ───────────────────────────────────────────────────────────
    def _tool_context(self, node_id: Any = None) -> ToolContext:
        anchor = node_id if node_id is not None else self.node_id
        local = None
        try:
            if anchor is not None:
                resolved = self.graph.resolve(anchor)
                if resolved is not None:
                    local = self.graph.materialize_local(resolved, Config.LOCAL_DEPTH)
        except Exception:  # noqa: BLE001
            pass
        return ToolContext(
            workspace_root=str(Config.WORKSPACE_ROOT),
            session_id=self._turn["turn_id"] if self._turn else "",
            node_id=anchor,
            local_graph=local,
            encoder=self.encoder,
            agent=self,
            extra={"graph": self.graph, "encoder": self.encoder,
                   "store": self.store},
        )

    def _maybe_compact(self) -> None:
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        remaining = Config.MAX_CONTEXT - total_chars // 4
        if remaining < Config.COMPACT_THRESHOLD and len(self.messages) > 15:
            keep = self.messages[-10:]
            sys_msg = self.messages[0]
            parts = []
            for m in self.messages[1:-10]:
                if m["role"] == "user":
                    parts.append(f"U: {str(m.get('content', ''))[:120]}")
                elif m["role"] == "tool":
                    parts.append(f"T: {str(m.get('content', ''))[:60]}")
            note = f"[context compacted: {len(self.messages) - 10} older messages] " + " | ".join(parts[-20:])
            new_sys = {"role": "system", "content": sys_msg["content"] + "\n\n" + note}
            self.messages = [new_sys] + keep

    def bind_node(self, node_id: Any) -> "AgentEngine":
        """Re-bind the engine to another anchor node (re-anchor for multi-round)."""
        self.node_id = node_id
        self.name = f"agent[{node_id}]"
        return self
