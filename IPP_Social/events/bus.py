"""
events.bus — the streaming event bus (data: social_database/events/).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from IPP_Social.paths import EVENTS_DIR
from IPP_Social.util import now_iso, read_text

EVENT_TYPES: list[str] = [
    "agent_joined", "card_commented", "constraints_updated",
    "goal_created", "task_created", "task_updated",
    "message_posted", "push_subscribed", "push_unsubscribed",
    "push_delivered",
]


class SocialEvent:
    """One append-only event (seq = the stream cursor)."""

    def __init__(self, seq: int = 0, type: str = "", agent_id: str = "",
                 payload: dict | None = None, ts: str | None = None):
        self.seq = int(seq)
        self.type = type
        self.agent_id = agent_id
        self.payload = dict(payload or {})
        self.ts = ts or now_iso()

    def to_dict(self) -> dict:
        return {"seq": self.seq, "type": self.type,
                "agent_id": self.agent_id, "payload": dict(self.payload),
                "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "SocialEvent":
        return cls(seq=d.get("seq", 0), type=d.get("type", ""),
                   agent_id=d.get("agent_id", ""),
                   payload=d.get("payload", {}), ts=d.get("ts"))


class SocialStream:
    """A live iterator over the event bus (streaming mode).

    Yields new events as they are appended, polling every ``poll_s``
    seconds until ``timeout_s`` elapses (0 = run until abandoned).
    """

    def __init__(self, bus: "EventBus", since: int = 0,
                 timeout_s: float = 0.0, poll_s: float = 0.2):
        self.bus = bus
        self.since = int(since)
        self.timeout_s = float(timeout_s)
        self.poll_s = float(poll_s)

    def __iter__(self):
        cursor = self.since
        deadline = (time.time() + self.timeout_s
                    if self.timeout_s and self.timeout_s > 0 else None)
        while True:
            for ev in self.bus.since(cursor):
                yield ev.to_dict()
                cursor = ev.seq
            if deadline is not None and time.time() >= deadline:
                break
            time.sleep(self.poll_s)


class EventBus:
    """Thread-safe append-only event bus (seq = line number)."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else EVENTS_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._path = self.root / "events.jsonl"
        self._lock = threading.RLock()

    def append(self, type: str, agent_id: str = "",
               payload: dict | None = None) -> int:
        """Append an event; returns its seq (the stream cursor)."""
        with self._lock:
            seq = 0
            if self._path.exists():
                with self._path.open("r", encoding="utf-8") as fh:
                    for _ in fh:
                        seq += 1
            ev = SocialEvent(seq=seq + 1, type=type, agent_id=agent_id,
                             payload=payload)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
            return ev.seq

    def since(self, seq: int = 0, limit: Optional[int] = None
              ) -> list[SocialEvent]:
        """Events after `seq` (buffered stream read)."""
        with self._lock:
            events: list[SocialEvent] = []
            if self._path.exists():
                with self._path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = SocialEvent.from_dict(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                        if ev.seq > seq:
                            events.append(ev)
        if limit is not None:
            events = events[-limit:]
        return events

    def last_seq(self) -> int:
        with self._lock:
            last = 0
            if self._path.exists():
                for line in read_text(self._path).splitlines():
                    line = line.strip()
                    if line:
                        try:
                            last = json.loads(line).get("seq", last)
                        except json.JSONDecodeError:
                            continue
            return last

    def stream(self, since: int = 0, timeout_s: float = 0.0) -> SocialStream:
        """A live iterator over new events."""
        return SocialStream(self, since=since, timeout_s=timeout_s)
