"""
IPP_Social.social_activity — the plug-and-play IPP v0.2.8 social component.

A single IPP node (``social_activity``) that ManyAgents agents connect
to through IPP. Six channels:

  card        — Agent Cards: registration, discovery, cross-agent comments
  profile     — the three agent properties: capacity (10-dim identity),
                random property (10-dim mean/variance vector), constraints
                (mutable physical vector, validated)
  tasks       — shared goal folders; individual tasks are .md files with
                a Version Control Log at the bottom
  chat_board  — the global chat board (broadcast to every agent)
  events      — the streaming event bus (buffered or live)
  a2a         — the four formal A2A modes: sync (declared, disabled),
                async (task-based, enabled), stream (enabled),
                push (chat-board scoped)

The functionality lives in separate module folders inside IPP_Social
(``agents/``, ``task_manager/``, ``chat_board/``, ``events/``, ``a2a/``);
the data lives in the social database (``social_database/``). See
README.md for the full contract.
"""
from __future__ import annotations

from typing import Any, Optional

from IPP_Social.social_activity.construct import (
    build_social_components, create_social_node,
)

__version__ = "0.2.0"
__all__ = ["SocialActivity", "create_social_node", "build_social_components",
           "__version__"]


class SocialActivity:
    """The plug-and-play facade: IPP node + shared module instances.

    Every method goes through the IPP guardrail envelope
    (``node.invoke`` → executor → GuardedOutput); the returned value is
    the envelope's payload.
    """

    def __init__(self, db_root: Optional[Path | str] = None,
                 dataset_root: Optional[Path | str] = None,
                 context=None):
        self.node, self.components = create_social_node(
            db_root=db_root, dataset_root=dataset_root, context=context)
        self.dataset = self.components["dataset"]
        self.tasks = self.components["tasks"]
        self.chat = self.components["chat"]
        self.events = self.components["events"]
        self.push = self.components["push"]
        self.a2a_ctx = self.components["a2a_ctx"]

    # ── raw IPP surface ──────────────────────────────────────────────────
    def invoke(self, channel: str, payload: Any,
               context: Optional[dict] = None) -> Any:
        """Invoke a channel through the guardrail envelope."""
        return self.node.invoke(channel, payload, context).payload

    @staticmethod
    def _clean(payload: dict) -> dict:
        """Drop None values so optional fields pass the payload schemas."""
        return {k: v for k, v in payload.items() if v is not None}

    def verify(self) -> list[str]:
        """17-invariant verification; [] = ALL 17 OK."""
        return self.node.verify()

    def audit_ok(self) -> bool:
        """True when every channel's hash-chained audit log verifies."""
        return all(ex.audit_verify()
                   for ex in self.node.executors.values())

    def summary(self) -> str:
        return self.node.summary()

    # ── card: registration / discovery / comments ────────────────────────
    def register_agent(self, agent_id: str, name: str = "",
                       capacity: Optional[dict] = None,
                       random_property: Optional[dict] = None,
                       constraints: Optional[dict] = None,
                       bio: str = "", overwrite: bool = False) -> dict:
        return self.invoke("card", self._clean({
            "op": "register", "agent_id": agent_id, "name": name or agent_id,
            "capacity": capacity, "random_property": random_property,
            "constraints": constraints, "bio": bio, "overwrite": overwrite}))

    def discover(self, agent_id: Optional[str] = None) -> dict:
        if agent_id:
            return self.invoke("card", {"op": "get", "agent_id": agent_id})
        return self.invoke("card", {"op": "list"})

    def comment_card(self, target_agent_id: str, author_id: str,
                     text: str) -> dict:
        return self.invoke("card", self._clean({
            "op": "comment", "target_agent_id": target_agent_id,
            "author_id": author_id, "text": text}))

    # ── profile: the three agent properties ──────────────────────────────
    def get_profile(self, agent_id: str) -> dict:
        return self.invoke("profile", {"op": "get", "agent_id": agent_id})

    def update_constraints(self, agent_id: str,
                           position: Optional[dict] = None,
                           resources: Optional[dict] = None) -> dict:
        return self.invoke("profile", self._clean({
            "op": "update_constraints", "agent_id": agent_id,
            "constraints": self._clean({"position": position,
                                        "resources": resources})}))

    # ── shared task management ───────────────────────────────────────────
    def create_goal(self, title: str, description: str = "",
                    owner_agent_id: str = "",
                    goal_id: Optional[str] = None) -> dict:
        return self.invoke("tasks", self._clean({
            "op": "create_goal", "title": title, "description": description,
            "owner_agent_id": owner_agent_id, "goal_id": goal_id}))

    def list_goals(self) -> dict:
        return self.invoke("tasks", {"op": "list_goals"})

    def get_goal(self, goal_id: str) -> dict:
        return self.invoke("tasks", {"op": "get_goal", "goal_id": goal_id})

    def create_task(self, goal_id: str, title: str,
                    description: str = "", assignee_agent_id: str = "",
                    task_id: Optional[str] = None,
                    author_agent_id: str = "",
                    depends_on: Optional[list] = None) -> dict:
        return self.invoke("tasks", self._clean({
            "op": "create_task", "goal_id": goal_id, "title": title,
            "description": description,
            "assignee_agent_id": assignee_agent_id, "task_id": task_id,
            "author_agent_id": author_agent_id, "depends_on": depends_on}))

    def update_task(self, goal_id: str, task_id: str,
                    author_agent_id: str, status: Optional[str] = None,
                    note: Optional[str] = None,
                    assignee: Optional[str] = None) -> dict:
        return self.invoke("tasks", self._clean({
            "op": "update_task", "goal_id": goal_id, "task_id": task_id,
            "author_agent_id": author_agent_id, "status": status,
            "note": note, "assignee_agent_id": assignee}))

    def get_task(self, goal_id: str, task_id: str) -> dict:
        return self.invoke("tasks", {"op": "get_task", "goal_id": goal_id,
                                     "task_id": task_id})

    def list_tasks(self, goal_id: str,
                   status: Optional[str] = None) -> dict:
        return self.invoke("tasks", self._clean({
            "op": "list_tasks", "goal_id": goal_id, "status": status}))

    # ── global chat board ────────────────────────────────────────────────
    def post_message(self, author_agent_id: str, text: str,
                     tags: Optional[list] = None) -> dict:
        return self.invoke("chat_board", self._clean({
            "op": "post", "author_agent_id": author_agent_id, "text": text,
            "tags": tags}))

    def get_messages(self, limit: Optional[int] = None) -> dict:
        return self.invoke("chat_board", self._clean({"op": "get",
                                                      "limit": limit}))

    def get_messages_since(self, after_id: int = 0) -> dict:
        return self.invoke("chat_board", {"op": "get_since",
                                          "after_id": after_id})

    # ── events: streaming ────────────────────────────────────────────────
    def stream_events(self, since: int = 0, live: bool = False,
                      timeout_s: float = 0.0) -> Any:
        return self.invoke("events", {"since": since, "live": live,
                                      "timeout_s": timeout_s})

    # ── a2a: the four formal interaction modes ───────────────────────────
    def a2a(self, mode: str, **kwargs) -> Any:
        return self.invoke("a2a", self._clean({"mode": mode, **kwargs}))

    def a2a_async_submit(self, from_agent_id: str, goal_id: str,
                         message: str, title: str = "handoff",
                         to_agent_id: str = "",
                         task_id: Optional[str] = None) -> dict:
        return self.a2a("async", action="submit", from_agent_id=from_agent_id,
                        goal_id=goal_id, message=message, title=title,
                        to_agent_id=to_agent_id, task_id=task_id)

    def a2a_async_status(self, from_agent_id: str, goal_id: str,
                         task_id: str) -> dict:
        return self.a2a("async", action="status", from_agent_id=from_agent_id,
                        goal_id=goal_id, task_id=task_id)

    def a2a_push_subscribe(self, agent_id: str, target: str = "chat_board"
                           ) -> dict:
        return self.a2a("push", action="subscribe", agent_id=agent_id,
                        target=target)

    def a2a_push_inbox(self, agent_id: str) -> dict:
        return self.a2a("push", action="inbox", agent_id=agent_id)
