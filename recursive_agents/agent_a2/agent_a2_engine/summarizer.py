"""
agent_a1_engine.summarizer — Intelligent Context Compaction

Equivalent to assets/copilot_agent_engine/summarizer.py.

When the conversation context exceeds thresholds, compacts older
messages into structured summaries, preserving:
  - Tool call results (compressed)
  - Key decisions
  - Construction state
  - Error patterns for improvement
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import time


@dataclass
class SummaryResult:
    """Result of context summarization."""
    summary: str = ""
    original_char_count: int = 0
    compacted_char_count: int = 0
    messages_summarized: int = 0
    tool_calls_summarized: int = 0
    key_decisions: list[str] = field(default_factory=list)
    errors_preserved: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class ContextSummarizer:
    """Compacts conversation context to stay within token budgets.

    Configurable thresholds:
      - COMPACT_THRESHOLD: chars before compaction triggers
      - MAX_CONTEXT: absolute max chars (hard cutoff)
      - KEEP_RECENT: number of most recent messages to preserve verbatim
    """

    COMPACT_THRESHOLD: int = 100_000
    MAX_CONTEXT: int = 500_000
    KEEP_RECENT: int = 8
    TRUNCATE_TOOL_RESULT: int = 500

    def __init__(self, compact_threshold: int = 100_000,
                 max_context: int = 500_000):
        self.compact_threshold = compact_threshold
        self.max_context = max_context
        self._summaries: list[SummaryResult] = []

    def should_compact(self, messages: list[dict]) -> bool:
        """Check if compaction is needed."""
        total = sum(len(str(m.get("content", ""))) for m in messages)
        return total > self.compact_threshold

    def compact(self, messages: list[dict]) -> tuple[list[dict], SummaryResult]:
        """Compact messages, returning reduced list and summary.

        Strategy:
          1. Keep the most recent KEEP_RECENT messages verbatim.
          2. Summarize older messages into structured notes.
          3. Preserve tool call results (truncated).
          4. Extract key decisions and errors.
        """
        if len(messages) <= self.KEEP_RECENT:
            return messages, SummaryResult()

        original_chars = sum(len(str(m.get("content", ""))) for m in messages)

        # Split: recent (keep) vs older (summarize)
        recent = messages[-self.KEEP_RECENT:]
        older = messages[:-self.KEEP_RECENT]

        # Extract tool calls from older messages
        tool_calls = []
        key_decisions = []
        errors = []
        for m in older:
            content = str(m.get("content", ""))
            role = m.get("role", "")
            if role == "tool" or "tool_call" in str(m):
                tool_calls.append(self._truncate(content))
            if "PASS" in content or "OK" in content or "complete" in content.lower():
                key_decisions.append(self._truncate(content))
            if "FAIL" in content or "error" in content.lower() or "Exception" in content:
                errors.append(self._truncate(content))

        # Build summary
        summary_parts = [
            f"[Context Compaction: {len(older)} earlier messages summarized]",
            f"Tool calls in compacted region: {len(tool_calls)}",
        ]
        if key_decisions:
            summary_parts.append(f"Key outcomes: {'; '.join(key_decisions[-5:])}")
        if errors:
            summary_parts.append(f"Errors: {'; '.join(errors[-3:])}")

        summary_text = "\n".join(summary_parts)
        summary_msg = {"role": "system", "content": summary_text}

        result = SummaryResult(
            summary=summary_text,
            original_char_count=original_chars,
            compacted_char_count=sum(len(str(m.get("content", ""))) for m in recent) + len(summary_text),
            messages_summarized=len(older),
            tool_calls_summarized=len(tool_calls),
            key_decisions=key_decisions[-5:],
            errors_preserved=errors[-3:],
        )
        self._summaries.append(result)

        return [summary_msg] + recent, result

    def _truncate(self, text: str, max_len: int = 300) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "…"

    @property
    def history(self) -> list[SummaryResult]:
        return list(self._summaries)
