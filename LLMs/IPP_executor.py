"""
LLMs.IPP_executor — the IPP Executors (Ξ_k) of the LLM node.

LLM-specific guardrails on top of the base envelope: token/cost accounting
in the audit record, and a per-call latency soft-cap. The base class already
enforces ι → π → Ω → ι → ρ → τ* with hash-chained provenance (Axiom X1–X9).
"""
from __future__ import annotations

import time

from IPP.IPP_executor import IPPExecutor


class LLMExecutor(IPPExecutor):
    """Ξ for an LLM channel — adds token accounting to the audit record."""

    def invoke(self, payload, context=None, envelope=None,
               source_channel=None):
        self._invoke_t0 = time.time()
        return super().invoke(payload, context, envelope, source_channel)

    def _record_extras(self, record: dict, envelope, out) -> None:
        """Token + latency accounting, added BEFORE the record is hashed."""
        if isinstance(out, dict):
            usage = out.get("usage") or {}
            record["tokens"] = usage.get("total_tokens", 0)
            record["latency_ms"] = round(
                (time.time() - getattr(self, "_invoke_t0", time.time())) * 1000)
