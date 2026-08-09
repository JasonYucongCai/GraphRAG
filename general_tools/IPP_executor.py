"""
tools.IPP_executor — the IPP Executors (Ξ_k) of the tools node.

Shared-runtime guardrails on top of the base envelope: every audit record
additionally carries the ``op`` (the operation family), the ``tool`` (the
executed tool name on the invoke channel) and the calling ``agent``
(when identified), so the hash-chained audit trail of the shared runtime
is queryable per operation / per tool / per agent. The base class already
enforces ι → π → Ω → ι → ρ → τ* (Axiom X1–X9).
"""
from __future__ import annotations

from IPP.IPP_executor import IPPExecutor


class ToolsExecutor(IPPExecutor):
    """Ξ for a tools-node channel — op + tool + agent accounting."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        """Add op/tool/agent to the record BEFORE it is hashed (Axiom X3 —
        the hash covers the extras)."""
        payload = getattr(envelope, "payload", None)
        if isinstance(payload, dict):
            record["op"] = payload.get("op", "")
            if payload.get("tool"):
                record["tool"] = payload["tool"]
            if payload.get("agent_id"):
                record["agent"] = payload["agent_id"]
