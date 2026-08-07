"""
portal.IPP_executor — the IPP Executors (Ξ_k) of the portal node.

``PortalExecutor`` stamps the portal op/agent into the hash-chained
audit record (via ``_record_extras``, called before hashing).
"""
from __future__ import annotations

from ipp.IPP_executor import IPPExecutor

_PORTAL_FIELDS = ("op", "agent_id", "goal_id", "goal", "instructions")


class PortalExecutor(IPPExecutor):
    """Ξ for a portal channel — records op/agent/goal in the audit."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        payload = envelope.payload
        if isinstance(payload, dict):
            for key in _PORTAL_FIELDS:
                value = payload.get(key)
                if value:
                    record[f"portal_{key}"] = value
        if isinstance(out, dict):
            if "ok" in out and not out.get("ok"):
                record["portal_error"] = out.get("error")
            if "goal_id" in out:
                record["portal_goal_id"] = out["goal_id"]
            if "agents" in out and isinstance(out["agents"], list):
                record["portal_agents"] = len(out["agents"])
