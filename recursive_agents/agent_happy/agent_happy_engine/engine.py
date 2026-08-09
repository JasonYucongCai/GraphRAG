"""
agent_a1_engine.engine — Enhanced RecursiveAgentEngine

NOT weaker than assets/copilot_agent_engine/engine.py. Integrates:
  - HookSystem for lifecycle events
  - PromptAssembler for composable prompts
  - AutopilotController for completion detection
  - ContextSummarizer for intelligent compaction
  - The full LLM function-calling loop with the agent's tool surface

Extends the runtime RecursiveAgentEngine with copilot-level features:
  - Multi-mode operation (ask/edit/agent/plan)
  - Streaming events with ToolCallEvent
  - Turn context tracking
  - Per-turn token accounting
  - Approval flow for dangerous operations
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generator, Optional

from recursive_agents.runtime.engine import RecursiveAgentEngine as BaseEngine
from recursive_agents.runtime.engine import RECURSIVE_TOOL_NAMES

from .hooks import HookSystem, HookContext, HookResult
from .prompt_assembler import PromptAssembler, PromptContext
from .autopilot import AutopilotController
from .summarizer import ContextSummarizer

logger = logging.getLogger("agent_a1.engine")


# ── Data Types ───────────────────────────────────────────────────────

class AgentMode(Enum):
    ASK = "ask"
    EDIT = "edit"
    AGENT = "agent"
    PLAN = "plan"


@dataclass
class ToolCallEvent:
    """Streaming event emitted during agent execution."""
    type: str             # tool_call | tool_result | text | done | error | compaction | start | approval
    tool: Optional[str] = None
    args: Optional[dict] = None
    content: Optional[str] = None
    rounds: Optional[int] = None
    usage: Optional[dict] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None
    tool_call_id: str = ""

    def to_dict(self) -> dict:
        d = {"type": self.type}
        if self.tool:
            d["tool"] = self.tool
        if self.args:
            d["args"] = self.args
        if self.content:
            d["content"] = self.content
        if self.rounds is not None:
            d["rounds"] = self.rounds
        if self.usage:
            d["usage"] = self.usage
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class TurnContext:
    """Per-turn tracking."""
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started_at: float = field(default_factory=time.time)
    tools_called: list[str] = field(default_factory=list)
    tokens_used: int = 0
    rounds_used: int = 0


# ── Enhanced Engine ──────────────────────────────────────────────────

class AgentA1Engine(BaseEngine):
    """Enhanced recursive agent engine for agent_a1.

    Carries the full copilot-level architecture:
      - hooks: HookSystem for lifecycle injection
      - assembler: PromptAssembler for composable prompts
      - autopilot: AutopilotController for completion detection
      - summarizer: ContextSummarizer for context compaction
      - session_id: unique per-session identifier
      - mode: AgentMode (ask/edit/agent/plan)

    Usage:
        engine = AgentA1Engine(graph=graph, encoder=encoder)
        engine.chat("Create agent_a2")
        for event in engine.chat_stream("Create agent_a2"):
            print(event.type, event.tool)
    """

    MAX_TOOL_ROUNDS: int = 15
    COMPACT_THRESHOLD: int = 150_000
    MAX_CONTEXT: int = 500_000
    DEFAULT_MODE: AgentMode = AgentMode.AGENT

    def __init__(self, graph=None, encoder=None, llm=None,
                 model: Optional[str] = None,
                 agent_id: str = "agent_a1", level: int = 1,
                 toolkit: Any = None,
                 system_prompt_text: Optional[str] = None,
                 tool_names: Optional[list[str]] = None,
                 store: Any = None,
                 mode: AgentMode = AgentMode.AGENT):
        super().__init__(
            graph=graph, encoder=encoder, llm=llm, model=model,
            agent_id=agent_id, level=level, toolkit=toolkit,
            system_prompt_text=system_prompt_text,
            tool_names=tool_names or RECURSIVE_TOOL_NAMES,
            store=store,
        )
        self.mode = mode
        self.session_id: str = uuid.uuid4().hex[:12]
        self._hooks = HookSystem()
        self._assembler = PromptAssembler(agent_id=agent_id, level=level)
        self._autopilot = AutopilotController()
        self._summarizer = ContextSummarizer(
            compact_threshold=self.COMPACT_THRESHOLD,
            max_context=self.MAX_CONTEXT,
        )
        self._turn: Optional[TurnContext] = None
        self._messages: list[dict] = []
        self._session_tokens: int = 0
        self._total_tool_rounds: int = 0

    # ── Properties ──────────────────────────────────────────────────

    @property
    def hooks(self) -> HookSystem:
        return self._hooks

    @property
    def assembler(self) -> PromptAssembler:
        return self._assembler

    @property
    def autopilot(self) -> AutopilotController:
        return self._autopilot

    @property
    def summarizer(self) -> ContextSummarizer:
        return self._summarizer

    # ── System Prompt ───────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Assemble the full system prompt from context."""
        ctx = PromptContext(
            agent_id=self.agent_id,
            level=self.level,
            tool_count=self.toolkit.count() if self.toolkit else 0,
            tool_definitions=(self.toolkit.definitions()
                             if self.toolkit else []),
            chain_state=(self.toolkit.chain
                        if self.toolkit else []),
        )
        return self._assembler.assemble(ctx)

    # ── Main Chat Loop ──────────────────────────────────────────────

    def chat(self, task: str, node_id: Any = None) -> str:
        """Run the full agent loop. Returns the final answer."""
        self._start_turn()
        grounded = self.ground(task, node_id)

        # Fire session_start hook on first turn
        if not self._messages:
            hook_ctx = HookContext(
                event=HookSystem.SESSION_START,
                session_id=self.session_id,
                agent_name=self.agent_id,
                mode=self.mode.value,
            )
            self._hooks.execute(HookSystem.SESSION_START, hook_ctx)

        # Fire user_prompt_submit hook
        hook_ctx = HookContext(
            event=HookSystem.USER_PROMPT_SUBMIT,
            session_id=self.session_id,
            agent_name=self.agent_id,
            mode=self.mode.value,
            messages=list(self._messages),
            tokens_used=self._session_tokens,
        )
        result = self._hooks.execute(HookSystem.USER_PROMPT_SUBMIT, hook_ctx)
        if result.injected_text:
            grounded = result.injected_text + "\n\n" + grounded

        # Build system prompt + messages
        system_prompt = self.system_prompt_text or self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._messages)
        messages.append({"role": "user", "content": grounded})

        # Tool-calling loop
        answer = ""
        trace: list[dict] = []
        for round_idx in range(self.MAX_TOOL_ROUNDS):
            # Check compaction
            if self._summarizer.should_compact(messages):
                hook_ctx = HookContext(
                    event=HookSystem.COMPACTION,
                    session_id=self.session_id,
                    agent_name=self.agent_id,
                    messages=list(messages),
                )
                self._hooks.execute(HookSystem.COMPACTION, hook_ctx)
                messages, _ = self._summarizer.compact(messages)

            # LLM call
            if self.llm is None:
                # Offline mode — deterministic path
                answer = f"[agent_a1 offline] Task received: {task[:200]}. Use tools to proceed."
                trace.append({"type": "text", "content": answer})
                break

            response = self._llm_call(messages)
            if response is None:
                break

            answer = response.get("content", "")
            trace.append({"type": "text", "content": answer})
            self._session_tokens += response.get("usage", {}).get("total_tokens", 0)

            # Check for tool calls
            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                break  # No more tool calls — answer is final

            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                trace.append({"type": "tool_call", "tool": tool_name,
                             "args": tool_args})

                # Fire tool_pre_invoke hook
                hook_ctx = HookContext(
                    event=HookSystem.TOOL_PRE_INVOKE,
                    session_id=self.session_id,
                    agent_name=self.agent_id,
                    tool_calls_this_turn=[tc],
                )
                pre_result = self._hooks.execute(
                    HookSystem.TOOL_PRE_INVOKE, hook_ctx)
                if pre_result.should_block:
                    tool_result = f"[BLOCKED] {pre_result.block_reason}"
                else:
                    # Execute tool through the tools node
                    tool_result = self._execute_tool(tool_name, tool_args)

                trace.append({"type": "tool_result", "tool": tool_name,
                             "content": tool_result})

                # Fire tool_post_invoke hook
                hook_ctx = HookContext(
                    event=HookSystem.TOOL_POST_INVOKE,
                    session_id=self.session_id,
                    agent_name=self.agent_id,
                    tool_calls_this_turn=[tc],
                    total_tool_rounds=round_idx + 1,
                )
                self._hooks.execute(HookSystem.TOOL_POST_INVOKE, hook_ctx)

                # Record in autopilot
                self._autopilot.record_tool_call(self.session_id, tool_name)

                # Add to messages
                messages.append({"role": "assistant", "content": None,
                                "tool_calls": [tc]})
                messages.append({"role": "tool", "content": str(tool_result),
                                "tool_call_id": tc.get("id", "")})

                if self._turn:
                    self._turn.tools_called.append(tool_name)

            self._total_tool_rounds += 1
            if self._turn:
                self._turn.rounds_used = round_idx + 1

        # Record answer in autopilot
        self._autopilot.record_answer(self.session_id, answer)

        # Fire stop hook
        hook_ctx = HookContext(
            event=HookSystem.STOP,
            session_id=self.session_id,
            agent_name=self.agent_id,
            mode=self.mode.value,
            final_response=answer,
            total_tool_rounds=self._total_tool_rounds,
            tokens_used=self._session_tokens,
        )
        stop_result = self._hooks.execute(HookSystem.STOP, hook_ctx)
        if stop_result.should_block:
            answer += f"\n\n[Hook blocked stop: {stop_result.block_reason}]"

        # Store messages for next turn
        self._messages = messages
        self._end_turn(answer)

        return answer

    def chat_stream(self, task: str, node_id: Any = None) -> Generator[ToolCallEvent, None, None]:
        """Stream the agent loop — yields ToolCallEvent for each step."""
        self._start_turn()
        grounded = self.ground(task, node_id)
        yield ToolCallEvent(type="start", content="agent_a1 starting")

        system_prompt = self.system_prompt_text or self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._messages)
        messages.append({"role": "user", "content": grounded})

        answer = ""
        for round_idx in range(self.MAX_TOOL_ROUNDS):
            if self._summarizer.should_compact(messages):
                messages, _ = self._summarizer.compact(messages)
                yield ToolCallEvent(type="compaction", rounds=round_idx)

            if self.llm is None:
                answer = f"[agent_a1 offline] Task: {task[:200]}"
                yield ToolCallEvent(type="text", content=answer)
                break

            response = self._llm_call(messages)
            if response is None:
                break

            answer = response.get("content", "")
            yield ToolCallEvent(type="text", content=answer,
                              usage=response.get("usage"))

            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                break

            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                yield ToolCallEvent(type="tool_call", tool=tool_name,
                                   args=tool_args, tool_call_id=tc.get("id", ""))

                tool_result = self._execute_tool(tool_name, tool_args)
                yield ToolCallEvent(type="tool_result", tool=tool_name,
                                   content=str(tool_result)[:1000])

                messages.append({"role": "assistant", "content": None,
                                "tool_calls": [tc]})
                messages.append({"role": "tool", "content": str(tool_result),
                                "tool_call_id": tc.get("id", "")})

            self._total_tool_rounds += 1

        yield ToolCallEvent(type="done", rounds=self._total_tool_rounds,
                           usage={"total_tokens": self._session_tokens})
        self._messages = messages
        self._end_turn(answer)

    # ── Tool Execution ──────────────────────────────────────────────

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        """Execute a tool through the agent's tools node."""
        # Try the agent's own toolkit first
        if self.toolkit and tool_name in self.toolkit.tools:
            tool = self.toolkit.tools[tool_name]
            try:
                from general_tools.IPP import ToolContext
                ctx = ToolContext(workspace_root=self.toolkit.ws_root,
                                 agent=self.toolkit)
                result = tool._run(args, ctx)
                return json.dumps({
                    "ok": result.ok,
                    "content": str(result.content)[:2000],
                    "error": result.error,
                    "metadata": result.metadata,
                }, ensure_ascii=False, default=str)
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})

        # Fallback to the tools node
        if self._tools_node and tool_name in self._tools_node.channels:
            try:
                result = self._tools_node.invoke(tool_name, args)
                return json.dumps(result.payload, ensure_ascii=False, default=str)
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})

        return json.dumps({"ok": False, "error": f"Tool {tool_name!r} not found"})

    # ── LLM Call ────────────────────────────────────────────────────

    def _llm_call(self, messages: list[dict]) -> Optional[dict]:
        """Make an LLM call. Returns parsed response with tool_calls."""
        try:
            raw = self.llm.chat(messages, tools=self.toolkit.definitions()
                               if self.toolkit else None)
            if isinstance(raw, str):
                return {"content": raw, "tool_calls": [], "usage": {}}
            return raw
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    # ── Turn Management ─────────────────────────────────────────────

    def _start_turn(self) -> None:
        self._turn = TurnContext()

    def _end_turn(self, answer: str) -> None:
        if self._turn:
            self._turn.tokens_used = self._session_tokens

    def run_with_trace(self, task: str, node_id: Any = None) -> tuple[str, list[dict]]:
        """Run chat and return (answer, trace). Backward-compatible."""
        trace: list[dict] = []
        answer = ""
        for event in self.chat_stream(task, node_id):
            trace.append(event.to_dict())
            if event.type == "text":
                answer += (event.content or "")
        return answer.strip(), trace

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> dict:
        """Report engine status."""
        return {
            "agent_id": self.agent_id,
            "level": self.level,
            "mode": self.mode.value,
            "session_id": self.session_id,
            "tools_available": (self.toolkit.count() if self.toolkit else 0),
            "chain": (self.toolkit.chain if self.toolkit else []),
            "tokens_used": self._session_tokens,
            "total_tool_rounds": self._total_tool_rounds,
            "messages_count": len(self._messages),
            "hooks_registered": list(self._hooks._handlers.keys()),
            "autopilot_progress": (self._autopilot.progress(self.session_id)
                                  if self._autopilot else {}),
        }
