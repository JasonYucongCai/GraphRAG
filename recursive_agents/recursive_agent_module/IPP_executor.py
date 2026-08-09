"""
recursive_agent_module.IPP_executor — Ξ executors for the recursive agent IPP node.

Enforces the guardrail envelope ι → π → Ω → ι → ρ → τ* (Axiom X1–X9)
for all five channels. Records channel identity + call metadata in the
hash-chained audit.
"""
from __future__ import annotations

from IPP.IPP_executor import IPPExecutor


class RecursiveAgentExecutor(IPPExecutor):
    """Ξ for the recursive agent module — records channel + timing."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        import time
        record["timestamp"] = time.time()
        if hasattr(envelope, "channel_id"):
            record["channel"] = envelope.channel_id
        if isinstance(out, dict):
            for key in ("agent_id", "chain", "elapsed", "tool_calls"):
                if key in out:
                    record[key] = out[key]
