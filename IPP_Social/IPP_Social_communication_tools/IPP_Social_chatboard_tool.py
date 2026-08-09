"""
chat_board.board — the global chat board (data: social_database/chat/).

``post`` broadcasts a message to every agent, emits a ``message_posted``
event, and fans out push notifications to subscribers (chat-board
scope — the ONLY push source).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from ManyAgents.agent_management.dataset import AgentDataset
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_push import PushNotifier
from IPP_Social.errors import UnknownAgent
from IPP_Social.IPP_Social_services_tools.IPP_Social_event_tool_bus import EventBus
from IPP_Social.paths import CHAT_DIR
from IPP_Social.util import now_iso, read_text


class Message:
    """One post on the global chat board.

    ``to_agent_id`` is the addressing: empty/\"chat_board\" = broadcast to
    the board, \"agents\" = addressed to every agent, otherwise a
    specific agent id (inter-agent message).
    """

    def __init__(self, message_id: int, author_agent_id: str, text: str,
                 tags: list | None = None, ts: str | None = None,
                 to_agent_id: str = ""):
        self.message_id = int(message_id)
        self.author_agent_id = author_agent_id
        self.text = text
        self.tags = list(tags or [])
        self.ts = ts or now_iso()
        self.to_agent_id = to_agent_id or ""

    def to_dict(self) -> dict:
        return {"message_id": self.message_id,
                "author_agent_id": self.author_agent_id, "text": self.text,
                "tags": list(self.tags), "ts": self.ts,
                "to_agent_id": self.to_agent_id}

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(message_id=d.get("message_id", 0),
                   author_agent_id=d.get("author_agent_id", ""),
                   text=d.get("text", ""), tags=d.get("tags", []),
                   ts=d.get("ts"), to_agent_id=d.get("to_agent_id", ""))


class ChatBoard:
    """Thread-safe global chat board with push fan-out."""

    def __init__(self, root: Path | str | None = None,
                 dataset: Optional[AgentDataset] = None,
                 event_bus: Optional[EventBus] = None,
                 push: Optional[PushNotifier] = None):
        self.root = Path(root) if root else CHAT_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._path = self.root / "board.jsonl"
        self.dataset = dataset or AgentDataset()
        self.event_bus = event_bus or EventBus()
        self.push = push or PushNotifier()
        self._lock = threading.RLock()

    # ── ops ──────────────────────────────────────────────────────────────
    def post(self, author_agent_id: str, text: str,
             tags: list | None = None, to_agent_id: str = "") -> dict:
        """Post to every agent; delivers to agent INBOXES by addressing.

        ``to_agent_id``:
          "" / "chat_board" → board broadcast — delivered to EVERY agent's
                              inbox (kind="board_broadcast") so the
                              conversation loop can react (incl. the user's
                              posts on the board)
          "agents"          → every agent's inbox (kind="broadcast")
          "<agent_id>"      → that agent's inbox (kind="direct_message")

        The inbox delivery is what powers the agent conversation loop
        (SocialResponder reads inboxes and the addressed agent replies).
        """
        if not author_agent_id or not text:
            from IPP_Social.errors import SocialError
            raise SocialError("post requires author_agent_id + text",
                              code="bad_request")
        # "user" and "portal" are the operator — they may post without an
        # agent card (the board is also the UI's chat input)
        if author_agent_id not in ("user", "portal") \
                and self.dataset.load_card(author_agent_id) is None:
            raise UnknownAgent(f"unknown agent {author_agent_id!r}",
                               agent_id=author_agent_id)
        msg = Message(message_id=self._next_id(),
                      author_agent_id=author_agent_id, text=text,
                      tags=list(tags or []), to_agent_id=to_agent_id or "")
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
        self.event_bus.append("message_posted", author_agent_id,
                              {"message_id": msg.message_id,
                               "text": text[:200]})

        def _notification(kind: str) -> dict:
            return {"kind": kind, "message_id": msg.message_id,
                    "author_agent_id": author_agent_id, "text": text,
                    "ts": msg.ts, "to_agent_id": msg.to_agent_id,
                    "tags": list(msg.tags)}

        delivered: list[str] = []
        to = msg.to_agent_id

        # 1) addressed delivery — the conversation loop's inboxes
        if to and to != "chat_board":
            targets: list[str] = []
            if to == "agents":
                targets = [c.agent_id for c in self.dataset.list_cards()
                           if c.agent_id != author_agent_id
                           and c.agent_id not in ("user", "portal")]
                kind = "broadcast"
            else:
                targets = [to]
                kind = "direct_message"
            for t in targets:
                self.push.deliver(t, _notification(kind))
                self.event_bus.append("push_delivered", t,
                                      {"message_id": msg.message_id,
                                       "kind": kind})
                delivered.append(t)
        else:
            # board broadcast ("" / "chat_board"): deliver to EVERY agent's
            # inbox so the conversation loop sees it — this is also how the
            # USER's posts on the board reach the agents
            for c in self.dataset.list_cards():
                if c.agent_id == author_agent_id \
                        or c.agent_id in ("user", "portal"):
                    continue
                self.push.deliver(c.agent_id, _notification("board_broadcast"))
                self.event_bus.append(
                    "push_delivered", c.agent_id,
                    {"message_id": msg.message_id,
                     "kind": "board_broadcast"})
                delivered.append(c.agent_id)

        # 2) subscriber fan-out (board broadcast / chat_board scope)
        for sub in self.push.subscribers():
            if sub == author_agent_id or sub in delivered:
                continue
            self.push.deliver(sub, _notification("chat_board_push"))
            self.event_bus.append("push_delivered", sub,
                                  {"message_id": msg.message_id,
                                   "kind": "chat_board_push"})
            delivered.append(sub)
        return {"message": msg.to_dict(), "push_delivered_to": delivered}

    def get(self, limit: Optional[int] = None) -> list[Message]:
        msgs = self._read_all()
        if limit is not None:
            msgs = msgs[-limit:]
        return msgs

    def get_since(self, after_id: int = 0) -> list[Message]:
        return [m for m in self._read_all() if m.message_id > after_id]

    def clear(self, scope: str = "all") -> dict:
        """Clear the board.

        ``scope``:
          "inter" — drop only agent-authored messages (keeps the user's);
          "all" / "board" — drop everything (global chat board).
        Returns {cleared: n, scope: scope}.
        """
        from IPP_Social.util import atomic_write
        with self._lock:
            msgs = self._read_all()
            if scope == "inter":
                keep = [m for m in msgs
                        if m.author_agent_id in ("user", "portal")]
                cleared = len(msgs) - len(keep)
            else:
                keep = []
                cleared = len(msgs)
            if keep:
                lines = "".join(
                    json.dumps(m.to_dict(), ensure_ascii=False) + "\n"
                    for m in keep)
                atomic_write(self._path, lines)
            else:
                self._path.unlink(missing_ok=True)
        return {"cleared": cleared, "scope": scope}

    # ── internals ────────────────────────────────────────────────────────
    def _read_all(self) -> list[Message]:
        with self._lock:
            if not self._path.exists():
                return []
            msgs = []
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            msgs.append(Message.from_dict(json.loads(line)))
                        except json.JSONDecodeError:
                            continue
            return msgs

    def _next_id(self) -> int:
        msgs = self._read_all()
        return (msgs[-1].message_id + 1) if msgs else 1
