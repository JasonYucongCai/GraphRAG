"""
codex_growth.tools.IPP_executor — the IPP Executors (Ξ_k) of the growth tools node.

Tool-specific audit extras: tool name and success flag in the record.
"""
from __future__ import annotations

from ipp.IPP_executor import IPPExecutor


class ToolExecutor(IPPExecutor):
    """Ξ for a tool channel — records tool identity in the audit."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        if payload.get("tool"):
            record["tool"] = payload["tool"]
        if isinstance(out, dict):
            record["tool_ok"] = bool(out.get("ok", True))
