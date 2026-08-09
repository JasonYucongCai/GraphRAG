"""
agent_a1_engine.hooks — Lifecycle Hook System

Equivalent to assets/copilot_agent_engine/hooks.py.

Hooks inject custom behavior at key lifecycle points:
  - session_start       — First turn of a session
  - user_prompt_submit  — Before the LLM call
  - stop                — Loop about to exit (can block continuation)
  - tool_pre_invoke     — Before a tool executes
  - tool_post_invoke    — After a tool executes
  - subagent_start      — Sub-agent spawned
  - subagent_stop       — Sub-agent loop about to exit
  - compaction          — Context compaction event
  - agent_construct     — When the next agent is being constructed
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger("agent_a1.hooks")


@dataclass
class HookResult:
    """Result of a hook execution."""
    event: str = ""
    should_block: bool = False
    block_reason: str = ""
    injected_text: str = ""
    modified_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookContext:
    """Context passed to hook handlers."""
    event: str = ""
    session_id: str = ""
    request_id: str = ""
    agent_name: str = "agent_a1"
    mode: str = "agent"
    messages: list[dict] = field(default_factory=list)
    tool_calls_this_turn: list[dict] = field(default_factory=list)
    total_tool_rounds: int = 0
    tokens_used: int = 0
    tokens_remaining: int = 0
    is_subagent: bool = False
    final_response: str = ""
    target_agent: str = ""          # for agent_construct events
    metadata: dict[str, Any] = field(default_factory=dict)


HookHandler = Callable[[HookContext], HookResult]


class HookSystem:
    """Manages hook registration and execution for agent_a1.

    Usage:
        hooks = HookSystem()
        hooks.register("stop", my_stop_handler)
        result = hooks.execute("stop", context)
        if result.should_block:
            print(f"Blocked: {result.block_reason}")
    """

    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    STOP = "stop"
    TOOL_PRE_INVOKE = "tool_pre_invoke"
    TOOL_POST_INVOKE = "tool_post_invoke"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    COMPACTION = "compaction"
    AGENT_CONSTRUCT = "agent_construct"

    def __init__(self):
        self._handlers: dict[str, list[HookHandler]] = {}
        self._metrics: dict[str, int] = {}

    def register(self, event: str, handler: HookHandler) -> None:
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        logger.debug(f"Registered hook for {event}: {handler.__name__}")

    def unregister(self, event: str, handler: HookHandler) -> None:
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def execute(self, event: str, context: HookContext) -> HookResult:
        """Execute all registered handlers for event. Returns merged result."""
        self._metrics[event] = self._metrics.get(event, 0) + 1
        handlers = self._handlers.get(event, [])
        merged = HookResult(event=event)
        for handler in handlers:
            try:
                result = handler(context)
                if result.should_block:
                    merged.should_block = True
                    merged.block_reason = result.block_reason or merged.block_reason
                if result.injected_text:
                    merged.injected_text += ("\n" + result.injected_text if merged.injected_text else result.injected_text)
                merged.modified_context.update(result.modified_context)
                merged.metadata.update(result.metadata)
            except Exception as e:
                logger.error(f"Hook {event} handler {handler.__name__} failed: {e}")
        return merged

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)
