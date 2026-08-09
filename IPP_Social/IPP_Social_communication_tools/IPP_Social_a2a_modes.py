"""
a2a.modes — the formal method registry + the dispatcher.

Every mode is coded as a formal method; enforcement is per-method:

  +----------+----------------------+-------------------------------------+
  | mode     | method               | currently                          |
  +==========+======================+=====================================+
  | sync     | SyncHandoff          | declared, NOT allowed              |
  | async    | AsyncTask            | allowed (task-based)               |
  | stream   | StreamSubscription   | allowed (event bus)                |
  | push     | PushNotification     | allowed, chat board only           |
  +----------+----------------------+-------------------------------------+
"""
from __future__ import annotations

from typing import Any, Optional

from ManyAgents.agent_management.dataset import AgentDataset
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_async_task import AsyncTask
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_push import PushNotifier
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_stream import StreamSubscription
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_sync import SyncHandoff
from IPP_Social.errors import SocialError
from IPP_Social.IPP_Social_services_tools.IPP_Social_event_tool_bus import EventBus
from IPP_Social.IPP_Social_services_tools.IPP_Social_tasks_manager import TaskManagement

# ════════════════════════════════════════════════════════════════════════
# The canonical registry of the four formal A2A methods
# ════════════════════════════════════════════════════════════════════════
# push is currently scoped to the global chat board only
PUSH_SCOPES: list[str] = ["chat_board"]

A2A_METHODS: dict[str, dict] = {
    "sync": {
        "name": "SyncHandoff",
        "description": (
            "Synchronous handoff: send the entire info to an agent and "
            "receive the entire response in one exchange."),
        "declared": True,
        "allowed": False,
        "reason": "declared for protocol conformance; not enabled in this "
                  "deployment",
        "schema": {"type": "object", "required": ["from_agent_id",
                                                  "to_agent_id", "message"]},
    },
    "async": {
        "name": "AsyncTask",
        "description": (
            "Asynchronous task-based interaction: submit a task into a "
            "goal folder, then poll it for updates; each poll responds "
            "with the task's current status."),
        "declared": True,
        "allowed": True,
        "schema": {"type": "object", "required": ["from_agent_id"]},
    },
    "stream": {
        "name": "StreamSubscription",
        "description": (
            "Streaming: subscribe to the social event bus and receive "
            "events as they happen (buffered or live)."),
        "declared": True,
        "allowed": True,
        "schema": {"type": "object"},
    },
    "push": {
        "name": "PushNotification",
        "description": (
            "Push notifications: register a subscription and receive "
            "notifications without polling. Currently scoped to the "
            "global chat board only."),
        "declared": True,
        "allowed": True,
        "scope": PUSH_SCOPES,
        "schema": {"type": "object", "required": ["agent_id"]},
    },
}

A2A_MODES: list[str] = list(A2A_METHODS)


class A2AContext:
    """The runtime peers the A2A methods operate on (shared instances)."""

    def __init__(self, tasks: Optional[TaskManagement] = None,
                 events: Optional[EventBus] = None,
                 push: Optional[PushNotifier] = None,
                 dataset: Optional[AgentDataset] = None):
        self.tasks = tasks or TaskManagement()
        self.events = events or EventBus()
        self.push = push or PushNotifier(event_bus=self.events)
        self.dataset = dataset or AgentDataset()

    def methods_table(self) -> list[dict]:
        return [{**spec, "mode": mode} for mode, spec in A2A_METHODS.items()]


# ════════════════════════════════════════════════════════════════════════
# The dispatcher — the a2a channel entry point
# ════════════════════════════════════════════════════════════════════════
def execute_a2a(payload: dict, ctx: A2AContext) -> Any:
    """Execute one of the four formal A2A methods."""
    mode = payload.get("mode")
    if mode not in A2A_METHODS:
        raise SocialError(f"unknown a2a mode {mode!r}; modes = {A2A_MODES}",
                          code="unknown_mode", modes=A2A_MODES)
    spec = A2A_METHODS[mode]
    if not spec["allowed"]:
        return {
            "ok": False, "mode": mode, "method": spec["name"],
            "declared": spec["declared"], "allowed": False,
            "error": "mode_not_allowed",
            "message": f"{mode}: {spec['reason']}",
        }
    if mode == "async":
        async_task = AsyncTask(ctx.tasks)
        if payload.get("action") == "status":
            return async_task.status(payload.get("from_agent_id", ""),
                                     payload.get("goal_id", ""),
                                     payload.get("task_id", ""))
        return async_task.submit(
            from_agent_id=payload.get("from_agent_id", ""),
            goal_id=payload.get("goal_id", ""),
            message=payload.get("message", ""),
            title=payload.get("title", "handoff"),
            to_agent_id=payload.get("to_agent_id", ""),
            task_id=payload.get("task_id"))
    if mode == "stream":
        return StreamSubscription(ctx.events).subscribe(
            since=int(payload.get("since", 0) or 0),
            live=bool(payload.get("live", False)),
            timeout_s=float(payload.get("timeout_s", 0) or 0))
    if mode == "push":
        return ctx.push.operate(payload, ctx.dataset)
    # sync — unreachable (disallowed above); keep the formal method callable
    return SyncHandoff().handoff(payload.get("from_agent_id"),
                                 payload.get("to_agent_id"),
                                 payload.get("message"))
