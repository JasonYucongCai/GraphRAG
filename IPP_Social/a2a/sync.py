"""
a2a.sync — formal method #1: SyncHandoff (synchronous).

Semantics: send the entire info to an agent and receive the entire
response in one exchange (handoff).

The method is DECLARED for protocol conformance but currently NOT
allowed in this deployment — invoking it returns a structured
``mode_not_allowed`` payload.
"""
from __future__ import annotations

from typing import Any


class SyncHandoff:
    """The synchronous handoff method (declared, currently disabled)."""

    name = "SyncHandoff"

    def handoff(self, from_agent_id: str | None = None,
                to_agent_id: str | None = None,
                message: Any = None) -> dict:
        """Attempt a synchronous handoff — rejected by deployment policy."""
        from IPP_Social.a2a.modes import A2A_METHODS
        spec = A2A_METHODS["sync"]
        return {
            "ok": False,
            "mode": "sync",
            "method": spec["name"],
            "declared": spec["declared"],
            "allowed": spec["allowed"],
            "error": "mode_not_allowed",
            "message": f"sync handoff: {spec['reason']}",
            "handoff": {"from_agent_id": from_agent_id,
                        "to_agent_id": to_agent_id,
                        "message": message},
        }
