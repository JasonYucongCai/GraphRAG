"""
social_activity.IPP_executor — the IPP Executors (Ξ_k) of the social node.

``SocialExecutor`` stamps social context (op, mode, agent ids, domain
errors) into the hash-chained audit record — via the ``_record_extras``
hook, which the base executor calls BEFORE hashing (Axiom X3).
``SocialStreamExecutor`` additionally records stream stats for the
``events`` channel.
"""
from __future__ import annotations

from IPP.IPP_executor import IPPExecutor
from IPP_Social.IPP_Social_services_tools.IPP_Social_event_tool_bus import SocialStream

_SOCIAL_FIELDS = ("op", "mode", "agent_id", "author_agent_id", "author_id",
                  "target_agent_id", "from_agent_id", "to_agent_id",
                  "goal_id", "task_id")


class SocialExecutor(IPPExecutor):
    """Ξ for a social channel — records op/mode/agent in the audit."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        payload = envelope.payload
        if isinstance(payload, dict):
            for key in _SOCIAL_FIELDS:
                value = payload.get(key)
                if value:
                    record[f"social_{key}"] = value
        if isinstance(out, dict):
            if "ok" in out and not out.get("ok"):
                record["social_error"] = out.get("error")
            if "cursor" in out:
                record["stream_cursor"] = out["cursor"]


class SocialStreamExecutor(SocialExecutor):
    """Ξ for the events channel — stream stats in the audit record."""

    def _record_extras(self, record: dict, envelope, out) -> None:
        super()._record_extras(record, envelope, out)
        if isinstance(out, SocialStream):
            record["stream_mode"] = "live"
            record["stream_since"] = out.since
        elif isinstance(out, dict) and "events" in out:
            record["stream_events"] = len(out["events"])
            record["stream_mode"] = "buffered"
