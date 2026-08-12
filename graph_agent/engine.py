"""
graph_agent.engine — the IPP agent engine (agentic loop).

A self-contained implementation of the Codex/Copilot-style agent loop:

    user message → prompt assembly → LLM call (via LLM IPP node) → tool
    execution (guardrail envelope + audit) → repeat → final answer

Key patterns:
  • Event-driven chat_stream() yielding ToolCallEvents (observable trace)
  • MAX_TOOL_ROUNDS bound + context auto-compaction
  • Session-scoped approval cache
  • Tool results truncated for context efficiency
  • IPP composition: AgentEngine ∘ ToolsNode ∘ KnowledgeGraph ∘ Encoder

The engine is bound to a graph + encoder so that graph tools operate on the
network. All LLM calls go through the LLM IPP node (NOT a raw provider),
so every call carries a hash-chained audit record.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Generator, Optional

from general_tools.config import Config
from general_tools.encoder import EncoderLayer
from general_tools.graph import KnowledgeGraph
from graph_agent.types import ToolCallEvent, ToolContext

logger = logging.getLogger("graph_agent.engine")

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


class LLMResult:
    """Minimal ChatCompletion-like envelope returned by _call_llm.

    Mirrors LLMs/deepseek/provider.py:LLMResult for backward compatibility
    with the existing engine loop — the engine works with .content,
    .tool_calls, .usage, .thinking regardless of whether the LLM is called
    through the IPP node or directly.
    """

    def __init__(self, content: str = "", tool_calls: Optional[list] = None,
                 usage: Optional[dict] = None, thinking: Optional[str] = None):
        """Create an LLMResult envelope from a raw content string, tool calls,
        usage stats, and optional thinking (DeepSeek reasoning).
        Mimics the OpenAI ChatCompletion shape — the engine loop
        consumes .content, .tool_calls, .usage, .thinking."""
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.usage = usage or {}
        self.thinking = thinking


class _LLMNodeAdapter:
    """Wraps an LLM IPP node to present the same .chat() / .chat_stream()
    interface the AgentEngine expects.

    Routes every call through the node's guardrail envelope (ι→π→Ω→ι→ρ→τ*)
    so all LLM calls carry hash-chained audit records. The return values are
    LLMResult-compatible (mirrors DeepSeekProvider's interface).
    """

    def __init__(self, llm_node, model: str = ""):
        self._node = llm_node
        self.model = model or "deepseek-v4-flash"
        self.name = f"deepseek:{self.model}"

    def chat(self, messages: list, tools=None, temperature=None,
             max_tokens=None) -> LLMResult:
        """Non-streaming call through the LLM IPP node's `chat` channel."""
        payload = {"messages": messages}
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = max_tokens
        guarded = self._node.invoke("chat", payload)
        data = guarded.payload if hasattr(guarded, "payload") else guarded
        if not isinstance(data, dict):
            data = {}
        return LLMResult(
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls", []),
            usage=data.get("usage", {}),
            thinking=data.get("thinking"),
        )

    def chat_stream(self, messages: list, tools=None, temperature=None,
                    max_tokens=None):
        """Streaming call through the LLM IPP node's `chat_stream` channel.

        The IPP node collects all streaming events into a list, then returns
        them. We replay the list as a generator for backward compatibility,
        with the final LLMResult arriving via StopIteration.value (PEP 380).
        """
        payload = {"messages": messages}
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = max_tokens
        guarded = self._node.invoke("chat_stream", payload)
        data = guarded.payload if hasattr(guarded, "payload") else guarded
        if not isinstance(data, dict):
            data = {}

        events = data.get("events", [])
        final = data.get("result") or {}

        # replay each (kind, data) tuple as the generator yields
        for kind, content in events:
            yield (kind, content)

        # PEP 380: the return value becomes StopIteration.value
        return LLMResult(
            content=final.get("content", ""),
            tool_calls=final.get("tool_calls", []),
            usage=final.get("usage", {}),
            thinking=final.get("thinking"),
        )

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        """Convenience: single-shot system+user completion."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = self.chat(messages, temperature=temperature)
        return result.content


class AgentEngine:
    """The agent engine bound to a graph network.

    All LLM calls go through the LLM IPP node (guardrail envelope + audit).
    Tools are dispatched through the shared tools IPP node.
    """

    name = "agent"

    def __init__(
        self,
        graph: KnowledgeGraph,
        encoder: EncoderLayer,
        llm: Any = None,                    # backward-compat: raw provider OR None
        llm_node: Any = None,               # preferred: IPP LLM node
        model: Optional[str] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        node_id: Any = None,
        tool_names: Optional[list] = None,
        store: Any = None,
    ):
        self.graph = graph
        self.encoder = encoder

        # ── LLM resolution: IPP node > raw provider > auto-construct ────
        if llm_node is not None:
            # PREFERRED: IPP LLM node (guardrails + audit)
            self.llm = _LLMNodeAdapter(llm_node, model=model or "")
        elif llm is not None:
            # Auto-detect: if the `llm=` value is an IPP node (has invoke()
            # but no chat()), wrap it in _LLMNodeAdapter so the engine's
            # .chat() / .chat_stream() calls route through the guardrail.
            if hasattr(llm, "invoke") and not hasattr(llm, "chat"):
                self.llm = _LLMNodeAdapter(llm, model=model or "")
            else:
                # BACKWARD-COMPAT: raw DeepSeekProvider (no IPP audit)
                self.llm = llm
        else:
            # AUTO: construct the LLM IPP node on the fly
            from LLMs import llm_node as _llm_node
            self.llm = _LLMNodeAdapter(_llm_node(), model=model or "")

        self.system_prompt = system_prompt
        self.node_id = node_id              # anchor node for this session
        self.tool_names = tool_names        # None = all shared tools
        self.store = store                  # NoteStore for database ops
        self.messages: list[dict] = []
        self._session_approvals: dict = {}
        self._session_tokens: int = 0
        self._turn: Optional[dict] = None
        self.name = f"agent[{node_id}]" if node_id is not None else "agent"
        # True  → streaming (per-token deltas via IPP node)
        # False → non-streaming (one call, many-agent default)
        self.llm_stream: bool = True
        self.run_limits = {
            "new_subjects": Config.MAX_NEW_SUBJECTS_PER_RUN,
            "new_refs_per_subject": Config.MAX_REFS_PER_SUBJECT_PER_RUN,
            "new_refs_total": Config.MAX_REFS_PER_RUN,
        }
        self._run_counts = {"new_subjects": 0, "new_refs": 0}

    # ── tool-layer integration (shared tools IPP node) ───────────────────
    def _tool_definitions(self, round_index: int = 1) -> list[dict]:
        """Tool definitions come from the tools node's F-file catalog."""
        from general_tools.construct import tools_node
        out = tools_node().invoke(
            "list", {"names": self.tool_names,
                     "round_index": round_index}).payload
        return out.get("definitions", []) if isinstance(out, dict) else []

    def _dispatch_tool(self, name: str, args: dict, ctx: "ToolContext") -> str:
        """Route through the tools node's invoke channel (guardrail envelope)."""
        from general_tools.construct import tools_node
        payload = {"tool": name, "args": args or {},
                   "session_id": ctx.session_id or "",
                   "workspace_root": ctx.workspace_root or ""}
        if ctx.extra.get("graph") is not None:
            payload["graph"] = ctx.extra["graph"]
        if ctx.extra.get("encoder") is not None:
            payload["encoder"] = ctx.extra["encoder"]
        agent = getattr(ctx, "agent", None)
        if agent is not None:
            payload["agent_id"] = (
                getattr(agent, "agent_id", None)
                or getattr(agent, "node_id", None) or "")
        out = tools_node().invoke("invoke", payload).payload
        if not isinstance(out, dict):
            return str(out)
        return str(out.get("content") or out.get("error")
                    or out.get("message") or "")

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
        """Run the agentic loop and return (final_answer, trace)."""
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
        """The agentic loop, yielding ToolCallEvents (observable trace)."""
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self._turn = {"turn_id": str(uuid.uuid4())[:8], "tools": [],
                      "tokens": 0, "started": time.time()}
        self.messages.append({"role": "user", "content": task})
        yield ToolCallEvent(type="start", content=f"turn {self._turn['turn_id']}")

        max_rounds = Config.MAX_TOOL_ROUNDS
        force_at = max(3, max_rounds - 2)

        for round_num in range(1, max_rounds + 1):
            self._maybe_compact()

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
                                yield ToolCallEvent(type="message_delta", content=data)
                            elif kind == "usage":
                                pass
                    except StopIteration as e:
                        result = e.value
                else:
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

            if content_delta:
                yield ToolCallEvent(type="message", content=content_delta)

            if result.usage:
                self._session_tokens += result.usage.get("total_tokens", 0)
                self._turn["tokens"] += result.usage.get("total_tokens", 0)

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

        reply = self.messages[-1].get("content", "") if self.messages else ""
        yield ToolCallEvent(type="text", content=reply or "[no answer produced]")
        yield ToolCallEvent(type="error", error="max tool rounds exceeded (forced answer)")

    # ── helpers ───────────────────────────────────────────────────────────
    def _tool_context(self, node_id: Any = None) -> ToolContext:
        """Build a ToolContext for the current turn.

        Materializes the depth-3 local graph of the anchor node and bundles
        it with the encoder, workspace root, session ID, and the agent
        reference so tools can access the full graph state during execution.

        Args:
            node_id: the graph node to anchor the local graph on (defaults to
                     self.node_id, the agent's session anchor)

        Returns:
            ToolContext with workspace_root, session_id, node_id, local_graph,
            encoder, agent, and extra (graph, encoder, store).
        """
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
        """Compress the message history when nearing context window exhaustion.

        Trigger: total characters in message contents exceed Config.MAX_CONTEXT
        minus COMPACT_THRESHOLD, AND more than 15 messages exist.

        Strategy: keep the system prompt header, keep the last 10 messages
        intact, replace older user/tool messages with a compacted summary
        block that preserves key facts while freeing context window space.
        """
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
        """Re-bind the engine to another anchor node for multi-turn sessions.

        Changes the agent's identity (self.name) and the default node for
        graph grounding. Subsequent chat() calls will anchor on this node
        unless explicitly overridden.

        Args:
            node_id: the graph node to re-anchor on.

        Returns:
            self (for method chaining: engine.bind_node(n).chat(task)).
        """
        self.node_id = node_id
        self.name = f"agent[{node_id}]"
        return self
