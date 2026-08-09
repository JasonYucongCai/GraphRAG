"""
swarm.responder — the SocialResponder daemon (the conversation loop).

Agents are now message-driven, not just task-driven:

  • Elena posts ``social_post to='Codex_20_Vivian'`` → the message is
    delivered to Vivian's INBOX (kind="direct_message", strict IPP
    through the social node's a2a push channel).
  • The responder watches every agent's inbox; when an addressed agent
    is idle, it enqueues a REPLY task: "Vivian, Elena said … — respond
    to her personally with social_post to='Codex_20_Vivian'."
  • Broadcasts (``to='agents'``) reach every inbox (kind="broadcast");
    an agent chooses to respond BASED ON ITS SOCIAL PROPERTY — the
    response probability is the agent's ``social`` capacity score, so
    social butterflies speak up and quiet agents stay quiet.

Guard rails (no runaway chatter):
  • only IDLE agents reply (not running, queue empty)
  • conversation depth capped per (author → agent) pair by
    ``max_reply_rounds`` (default 2)
  • the agent's own messages and user/portal messages never trigger
    replies; a reply task never re-broadcasts its answer

Inbox reads go through the social_activity node's guardrail envelope
(``a2a push inbox``), so the whole loop stays strict IPP v0.2.8.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Optional

logger = logging.getLogger("IPP.responder")


class SocialResponder:
    """Watches agent inboxes and enqueues conversation replies."""

    def __init__(self, swarm, settings, poll_s: float = 3.0,
                 social_node=None):
        self.swarm = swarm
        self.settings = settings
        self.poll_s = float(poll_s)
        self.social_node = social_node or swarm.social_node
        self._seen: dict[str, set] = {}          # agent_id → {message_id}
        self._depth: dict[tuple, int] = {}       # (author, agent) → rounds
        self._broadcast_responders: dict[int, set] = {}  # msg_id → {agents}
        self._social_cache: dict[str, float] = {}   # agent_id → social score
        self._stop = False
        self._thread: Optional[threading.Thread] = None

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._loop,
                                        name="social-responder",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    # ── the loop ─────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while not self._stop:
            try:
                self._poll()
            except Exception as exc:  # noqa: BLE001 — never kill the daemon
                logger.warning("responder poll failed: %s", exc)
            time.sleep(self.poll_s)

    # ── inbox reads (strict IPP: through the social node envelope) ───────
    def _inbox(self, agent_id: str) -> list[dict]:
        try:
            result = self.social_node.invoke(
                "a2a", {"mode": "push", "action": "inbox",
                        "agent_id": agent_id}).payload
            if isinstance(result, dict):
                return result.get("inbox", [])
        except Exception as exc:  # noqa: BLE001
            logger.debug("inbox read failed for %s: %s", agent_id, exc)
        return []

    def _social_score(self, agent_id: str) -> float:
        if agent_id in self._social_cache:
            return self._social_cache[agent_id]
        score = 40.0
        try:
            cards = self.social_node.invoke(
                "card", {"op": "list"}).payload
            for card in (cards.get("cards") or []):
                if card.get("agent_id") == agent_id:
                    score = float(card.get("capacity", {}).get("social", 40))
                    break
        except Exception:  # noqa: BLE001
            pass
        self._social_cache[agent_id] = score
        return score

    # ── polling ──────────────────────────────────────────────────────────
    def _poll(self) -> None:
        if not getattr(self.settings, "get", lambda k, d: d)(
                "social_responder", True):
            return
        max_rounds = int(getattr(self.settings, "get", lambda k, d: d)(
            "max_reply_rounds", 2))
        for agent_id, rt in self.swarm.runtimes.items():
            if rt.status == "running" or rt.pending > 0:
                continue                       # only idle agents reply
            seen = self._seen.setdefault(agent_id, set())
            for note in self._inbox(agent_id):
                mid = note.get("message_id")
                if mid is None or mid in seen:
                    continue
                seen.add(mid)
                author = note.get("author_agent_id") or ""
                kind = note.get("kind") or ""
                to = note.get("to_agent_id") or ""
                tags = note.get("tags") or []
                if not author or author == agent_id:
                    continue
                # system posts (swarm task completions, board ops) must NOT
                # trigger the conversation loop — only genuine messages do
                if any(t in ("swarm", "done", "system") for t in tags):
                    continue
                if author in ("user", "portal"):
                    # The USER posts on the global chat board (delivered as
                    # kind="board_broadcast"). Agents respond on the board —
                    # gated by social property + responder cap, so a few
                    # agents answer instead of all 20.
                    if kind == "board_broadcast":
                        self._maybe_reply(agent_id, author, note,
                                          direct=False,
                                          max_rounds=max_rounds,
                                          user_message=True)
                    continue
                if kind == "direct_message" and to == agent_id:
                    self._maybe_reply(agent_id, author, note, direct=True,
                                      max_rounds=max_rounds)
                elif kind == "broadcast" and to == "agents":
                    self._maybe_reply(agent_id, author, note, direct=False,
                                      max_rounds=max_rounds)
                # kind == "board_broadcast" from an agent → announcement;
                # no auto-reply (avoids echo chatter)

    # ── the reply decision ───────────────────────────────────────────────
    def _maybe_reply(self, agent_id: str, author: str, note: dict,
                     direct: bool, max_rounds: int,
                     user_message: bool = False) -> None:
        key = (author, agent_id)
        rounds = self._depth.get(key, 0)
        if rounds >= max_rounds:
            return
        if not direct:
            # broadcast: only a bounded number of agents answer, chosen by
            # their SOCIAL property — prevents discussion storms
            mid = int(note.get("message_id", 0) or 0)
            responders = self._broadcast_responders.setdefault(mid, set())
            cap = int(getattr(self.settings, "get", lambda k, d: d)(
                "max_broadcast_responders", 4))
            if len(responders) >= cap:
                return
            score = self._social_score(agent_id)
            seed = mid * 7919 + sum(ord(c) for c in agent_id)
            if random.Random(seed).random() > (score / 100.0) * 0.7:
                return
            responders.add(agent_id)
        self._depth[key] = rounds + 1
        text = note.get("text", "") or ""
        if direct:
            instruction = (
                f"[SOCIAL REPLY {rounds + 1}/{max_rounds}] {author} "
                f"({author}) sent YOU a direct message:\n\"{text[:300]}\"\n"
                f"Reply to {author} personally with social_post "
                f"to='{author}'. One short sentence is enough.")
        elif user_message:
            instruction = (
                f"[USER ON BOARD] The user just posted on the global chat "
                f"board:\n\"{text[:300]}\"\n"
                f"Respond to the user on the board with social_post "
                f"to='chat_board' — one short, friendly sentence is enough. "
                f"If the user asked a question, answer it briefly.")
        else:
            instruction = (
                f"[SOCIAL BROADCAST] {author} said to everyone:\n"
                f"\"{text[:300]}\"\n"
                f"If you have something relevant to say, reply DIRECTLY to "
                f"{author} with social_post to='{author}' (not to agents). "
                f"One short sentence is enough.")
        rt = self.swarm.runtimes.get(agent_id)
        if rt is None:
            return
        rt.enqueue({"task_id": None, "goal_id": None, "text": instruction,
                    "reply": True, "reply_to": author})
        rt.start()
        self.swarm.bus.emit("agent_reply_enqueued", agent_id,
                            {"to": author, "round": rounds + 1,
                             "text": instruction[:120]})
