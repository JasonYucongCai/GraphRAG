"""
ManyAgents.IPP_executor — the IPP Executor (Ξ_k) of the many_agents node.

One executor class for both channels. Every audit record carries the
``op`` (operation: start/stop/list/get/…) and ``agent_id`` when applicable.
The hash-chained audit trail is queryable per operation + per agent.
"""
from __future__ import annotations

from IPP.IPP_executor import IPPExecutor


class ManyAgentsExecutor(IPPExecutor):
    """Ξ for many_agents channels — op + agent_id in audit records."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        payload = getattr(envelope, "payload", None)
        if isinstance(payload, dict):
            record["op"] = payload.get("op", "")
            record["agent_id"] = payload.get("agent_id", "")
            record["goal_id"] = payload.get("goal_id", "")
        record["node"] = "many_agents"
