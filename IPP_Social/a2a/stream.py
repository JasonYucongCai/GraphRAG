"""
a2a.stream — formal method #3: StreamSubscription (streaming).

Subscribe to the social event bus: buffered events since a cursor, or a
live iterator (``SocialStream``) when ``live`` is true.
"""
from __future__ import annotations

from typing import Any, Optional

from IPP_Social.events.bus import EventBus


class StreamSubscription:
    """The streaming event-bus subscription method."""

    name = "StreamSubscription"

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or EventBus()

    def subscribe(self, since: int = 0, live: bool = False,
                  timeout_s: float = 0.0) -> Any:
        if not live:
            events = self.event_bus.since(since)
            return {
                "ok": True, "mode": "stream", "live": False,
                "events": [e.to_dict() for e in events],
                "cursor": self.event_bus.last_seq(),
            }
        return self.event_bus.stream(since=since, timeout_s=timeout_s)
