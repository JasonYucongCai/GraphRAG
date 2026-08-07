"""
a2a.push — formal method #4: PushNotification.

Notifications delivered without polling. Currently scoped to the global
chat board only: a chat-board post fans out to every subscriber's inbox
(``social_database/push/<agent>/inbox.jsonl``). Any other target is
rejected with ``push_scope_denied``.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from IPP_Social.agents.dataset import AgentDataset
from IPP_Social.errors import SocialError, UnknownAgent
from IPP_Social.events.bus import EventBus
from IPP_Social.paths import PUSH_DIR
from IPP_Social.util import atomic_write, read_text

# the only allowed notification target today
ALLOWED_PUSH_SCOPES: list[str] = ["chat_board"]


class PushNotifier:
    """Push subscriptions + per-agent inboxes (thread-safe)."""

    name = "PushNotification"

    def __init__(self, root: Path | str | None = None,
                 event_bus: Optional[EventBus] = None):
        self.root = Path(root) if root else PUSH_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.event_bus = event_bus
        self._lock = threading.RLock()

    # ── subscriptions ────────────────────────────────────────────────────
    def _subs_path(self) -> Path:
        return self.root / "subscriptions.json"

    def subscribe(self, agent_id: str) -> list[str]:
        with self._lock:
            subs = set(self._read_subs())
            subs.add(agent_id)
            atomic_write(self._subs_path(),
                         json.dumps(sorted(subs), ensure_ascii=False, indent=2))
        if self.event_bus is not None:
            self.event_bus.append("push_subscribed", agent_id)
        return sorted(subs)

    def unsubscribe(self, agent_id: str) -> list[str]:
        with self._lock:
            subs = set(self._read_subs())
            subs.discard(agent_id)
            atomic_write(self._subs_path(),
                         json.dumps(sorted(subs), ensure_ascii=False, indent=2))
        if self.event_bus is not None:
            self.event_bus.append("push_unsubscribed", agent_id)
        return sorted(subs)

    def subscribers(self) -> list[str]:
        with self._lock:
            return self._read_subs()

    def _read_subs(self) -> list[str]:
        path = self._subs_path()
        if not path.exists():
            return []
        try:
            return list(json.loads(read_text(path)))
        except (json.JSONDecodeError, TypeError):
            return []

    # ── inboxes ──────────────────────────────────────────────────────────
    def deliver(self, agent_id: str, notification: dict) -> None:
        """Append one notification to an agent's inbox."""
        with self._lock:
            inbox = self.root / agent_id / "inbox.jsonl"
            inbox.parent.mkdir(parents=True, exist_ok=True)
            with inbox.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(notification, ensure_ascii=False) + "\n")

    def inbox(self, agent_id: str) -> list[dict]:
        with self._lock:
            path = self.root / agent_id / "inbox.jsonl"
            if not path.exists():
                return []
            out = []
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            return out

    # ── the A2A push method ──────────────────────────────────────────────
    def operate(self, payload: dict,
                dataset: Optional[AgentDataset] = None) -> dict:
        """subscribe / unsubscribe / inbox, scoped to the chat board."""
        agent_id = payload.get("agent_id")
        if not agent_id:
            raise SocialError("push requires agent_id", code="bad_request")
        if dataset is not None and dataset.load_card(agent_id) is None:
            raise UnknownAgent(f"unknown agent {agent_id!r}",
                               agent_id=agent_id)
        action = payload.get("action", "subscribe")
        target = payload.get("target", "chat_board")
        if target not in ALLOWED_PUSH_SCOPES:
            return {
                "ok": False, "mode": "push",
                "error": "push_scope_denied",
                "message": (f"push notifications are currently scoped to "
                            f"{ALLOWED_PUSH_SCOPES} only; target "
                            f"{target!r} rejected"),
                "allowed_targets": ALLOWED_PUSH_SCOPES,
            }
        if action == "unsubscribe":
            subs = self.unsubscribe(agent_id)
            return {"ok": True, "mode": "push", "action": "unsubscribe",
                    "agent_id": agent_id, "target": target,
                    "subscribers": subs}
        if action == "inbox":
            return {"ok": True, "mode": "push", "action": "inbox",
                    "agent_id": agent_id, "target": target,
                    "inbox": self.inbox(agent_id)}
        subs = self.subscribe(agent_id)
        return {"ok": True, "mode": "push", "action": "subscribe",
                "agent_id": agent_id, "target": target,
                "inbox": f"push/{agent_id}/inbox.jsonl", "subscribers": subs}
