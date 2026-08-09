"""
agent_a1_engine.autopilot — Task Completion Detection

Equivalent to assets/copilot_agent_engine/autopilot.py.

Detects when a multi-step task has reached completion by monitoring:
  - Tool call patterns (construction sequence completeness)
  - Answer quality signals (OK/PASS in responses)
  - Invariant verification results
  - Chain state progression
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import re


@dataclass
class AutopilotState:
    """Tracks agent task progress for completion detection."""
    task_type: str = ""
    target_agent: str = ""
    steps_completed: list[str] = field(default_factory=list)
    steps_expected: list[str] = field(default_factory=list)
    tool_calls: int = 0
    rounds: int = 0
    all_invariants_ok: bool = False
    last_answer: str = ""
    completed: bool = False


class AutopilotController:
    """Monitors agent activity to detect task completion.

    For agent_a1, the primary task is constructing the next agent.
    The controller recognizes the construction sequence:
      agent_plan → agent_generate → agent_create → agent_evaluate
      → agent_test → agent_improve → agent_deploy → agent_status

    Completion is detected when:
      - All 8 construction steps have been called
      - The answer contains PASS/OK/completed
      - agent_status reports the new agent in the chain
    """

    CONSTRUCTION_SEQUENCE = [
        "agent_plan", "agent_generate", "agent_create",
        "agent_evaluate", "agent_test", "agent_improve",
        "agent_deploy", "agent_status",
    ]

    COMPLETION_PATTERNS = [
        re.compile(r"ALL\s+(17|INVARIANTS)\s+(OK|PASS)", re.IGNORECASE),
        re.compile(r"(?:agent|construction|deployment)\s+(?:complete|success|OK|done)", re.IGNORECASE),
        re.compile(r"(?:chain|all agents)\s+(?:verified|ready|complete)", re.IGNORECASE),
        re.compile(r"✅", re.IGNORECASE),
    ]

    def __init__(self):
        self._states: dict[str, AutopilotState] = {}

    def start_task(self, session_id: str, task_type: str = "construction",
                   target_agent: str = "") -> AutopilotState:
        """Initialize tracking for a new task."""
        state = AutopilotState(
            task_type=task_type,
            target_agent=target_agent,
            steps_expected=list(self.CONSTRUCTION_SEQUENCE),
        )
        self._states[session_id] = state
        return state

    def record_tool_call(self, session_id: str, tool_name: str) -> Optional[AutopilotState]:
        """Record a tool call and check for completion."""
        state = self._states.get(session_id)
        if state is None:
            return None
        state.tool_calls += 1
        if tool_name in self.CONSTRUCTION_SEQUENCE:
            if tool_name not in state.steps_completed:
                state.steps_completed.append(tool_name)
        self._check_completion(state)
        return state

    def record_answer(self, session_id: str, answer: str) -> Optional[AutopilotState]:
        """Record an answer and check for completion signals."""
        state = self._states.get(session_id)
        if state is None:
            return None
        state.last_answer = answer
        state.rounds += 1
        self._check_completion(state)
        return state

    def record_invariants(self, session_id: str, ok: bool) -> Optional[AutopilotState]:
        """Record invariant verification result."""
        state = self._states.get(session_id)
        if state is None:
            return None
        state.all_invariants_ok = ok
        self._check_completion(state)
        return state

    def _check_completion(self, state: AutopilotState) -> None:
        """Determine if the task is complete."""
        if state.completed:
            return

        # Check: all construction steps called
        all_steps = all(s in state.steps_completed
                        for s in self.CONSTRUCTION_SEQUENCE)

        # Check: invariants passed
        invariants_ok = state.all_invariants_ok

        # Check: answer signals completion
        answer_signals = any(p.search(state.last_answer)
                            for p in self.COMPLETION_PATTERNS) if state.last_answer else False

        # Completion criteria
        if all_steps and invariants_ok:
            state.completed = True
        elif all_steps and answer_signals:
            state.completed = True
        elif state.rounds >= 20:
            state.completed = True  # timeout

    def is_complete(self, session_id: str) -> bool:
        """Check if a task is complete."""
        state = self._states.get(session_id)
        return state.completed if state else False

    def progress(self, session_id: str) -> dict:
        """Get progress report."""
        state = self._states.get(session_id)
        if state is None:
            return {"completed": False, "progress": 0}
        total = len(state.steps_expected)
        done = len(state.steps_completed)
        return {
            "completed": state.completed,
            "progress": done / max(total, 1),
            "steps_done": state.steps_completed,
            "steps_remaining": [s for s in state.steps_expected
                               if s not in state.steps_completed],
            "tool_calls": state.tool_calls,
            "rounds": state.rounds,
            "invariants_ok": state.all_invariants_ok,
        }

    def clear(self, session_id: str) -> None:
        self._states.pop(session_id, None)
