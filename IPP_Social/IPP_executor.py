"""
IPP_Social.IPP_executor — the IPP Executor (Ξ_k) of the social node.

One unified executor class for all 11 channels. Every audit record carries
social context (op, agent_id, goal_id, mode, error) into the hash-chained
audit trail. Stream channels (events, monitor) additionally record stream
statistics.
"""
from __future__ import annotations

from IPP.IPP_executor import IPPExecutor

_SOCIAL_FIELDS = ("op", "mode", "agent_id", "author_agent_id", "author_id",
                  "target_agent_id", "from_agent_id", "to_agent_id",
                  "goal_id", "task_id")

_PORTAL_FIELDS = ("goal", "instructions")


class SocialExecutor(IPPExecutor):
    """Ξ for all social channels — op/agent/goal/error in audit records."""

    STREAM_CHANNELS = {"events", "monitor"}

    def _record_extras(self, record: dict, envelope, out) -> None:
        payload = getattr(envelope, "payload", None)
        if isinstance(payload, dict):
            for key in _SOCIAL_FIELDS:
                value = payload.get(key)
                if value:
                    record[f"social_{key}"] = value
            for key in _PORTAL_FIELDS:
                value = payload.get(key)
                if value:
                    record[f"portal_{key}"] = value
        if isinstance(out, dict):
            if "ok" in out and not out.get("ok"):
                record["social_error"] = out.get("error")
            if "cursor" in out:
                record["stream_cursor"] = out["cursor"]
            if "goal_id" in out:
                record["portal_goal_id"] = out["goal_id"]
            if "agents" in out and isinstance(out["agents"], list):
                record["portal_agents"] = len(out["agents"])
        record["node"] = "social"
        # stream stats for streaming channels
        if self.channel_id in self.STREAM_CHANNELS:
            if isinstance(out, dict) and "events" in out:
                record["stream_event_count"] = len(out["events"])
