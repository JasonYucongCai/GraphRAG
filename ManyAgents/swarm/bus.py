"""
swarm.bus — the in-memory swarm event bus (live activity for the portal).

The bus is the runtime backbone of the Multi Agent portal: every agent
activity event (thinking, tool call, tool result, message, done) is
appended with a monotonically increasing seq; the UI consumes it over
SSE via ``iter_live``. It mirrors nothing on disk — the persistent
social trail lives in the social_activity event bus (events channel).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Iterator, Optional

from IPP_Social.util import now_iso


class SwarmBus:
    """Thread-safe append-only in-memory event bus with live iteration."""

    def __init__(self, max_history: int = 5000):
        self._events: deque[dict] = deque(maxlen=max_history)
        self._seq = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)

    # ── emit ─────────────────────────────────────────────────────────────
    def emit(self, type_: str, agent_id: str = "",
             data: dict | None = None) -> int:
        """Append one event; returns its seq (the live cursor)."""
        with self._cond:
            self._seq += 1
            ev = {"seq": self._seq, "type": type_, "agent_id": agent_id,
                  "data": dict(data or {}), "ts": now_iso()}
            self._events.append(ev)
            self._cond.notify_all()
            return ev["seq"]

    # ── buffered read ────────────────────────────────────────────────────
    def since(self, seq: int = 0, limit: Optional[int] = None
              ) -> list[dict]:
        """All events after ``seq`` (the reconnect cursor)."""
        with self._lock:
            out = [e for e in self._events if e["seq"] > seq]
        if limit is not None:
            out = out[-limit:]
        return out

    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    # ── live read (SSE / portal monitor channel) ─────────────────────────
    def iter_live(self, since: int = 0, timeout_s: float = 0.0,
                  poll_s: float = 0.15) -> Iterator[dict]:
        """Yield new events as they are emitted.

        ``timeout_s`` > 0 bounds the lifetime (used by the portal monitor
        channel); 0 runs until the consumer stops reading.
        """
        cursor = int(since)
        deadline = (time.time() + timeout_s
                    if timeout_s and timeout_s > 0 else None)
        while True:
            with self._cond:
                while self._seq <= cursor:
                    if deadline is not None and time.time() >= deadline:
                        return
                    self._cond.wait(timeout=poll_s)
                events = [e for e in self._events if e["seq"] > cursor]
            for ev in events:
                cursor = ev["seq"]
                yield ev
            if deadline is not None and time.time() >= deadline:
                return
