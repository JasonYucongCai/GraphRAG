"""
codex_normal.engine.IPP_executor — the IPP Executors (Ξ_k) of the general engine.
"""
from __future__ import annotations

from ipp.IPP_executor import IPPExecutor


class AgentExecutor(IPPExecutor):
    """Ξ for an agent channel — records trace/tool-call stats in the audit."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        if isinstance(out, dict):
            trace = out.get("trace") or []
            record["trace_steps"] = len(trace)
            record["tool_calls"] = sum(
                1 for t in trace if t.get("type") == "tool_call")
