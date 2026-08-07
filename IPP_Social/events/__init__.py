"""
events — the streaming social event bus.

Append-only event log backed by ``social_database/events/events.jsonl``
(seq = line number). Supports buffered reads (``since``) and live
streaming via the ``SocialStream`` iterator.
"""
from __future__ import annotations

from IPP_Social.events.bus import EVENT_TYPES, EventBus, SocialEvent, SocialStream

__all__ = ["EVENT_TYPES", "EventBus", "SocialEvent", "SocialStream"]
