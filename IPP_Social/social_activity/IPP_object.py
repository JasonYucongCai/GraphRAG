"""
social_activity.IPP_object — the IPP Objects (Ω_k) of the social_activity node.

Each factory closes over the module facades bound in the GraphContext
(``dataset``, ``tasks``, ``chat``, ``events``, ``a2a_ctx``) and returns
a deterministic ``handler(payload, context)``. Domain errors
(``SocialError`` subclasses) are translated at this boundary into
structured ``{"ok": false, "error": code, ...}`` payloads.
"""
from __future__ import annotations

from typing import Any

from IPP_Social.a2a.modes import execute_a2a
from IPP_Social.agents.agent_card import AgentCard
from IPP_Social.agents.capacity import Capacity
from IPP_Social.agents.constraints import Constraints
from IPP_Social.agents.dataset import AgentDataset
from IPP_Social.agents.random_property import RandomProperty
from IPP_Social.errors import DuplicateAgent, SocialError
from IPP_Social.events.bus import EventBus, SocialStream
from IPP_Social.task_manager.manager import TaskManagement


def _emit(events: EventBus, type_: str, agent_id: str = "",
          payload: dict | None = None) -> int:
    return events.append(type_, agent_id, payload)


# ════════════════════════════════════════════════════════════════════════
# card — register / get / list / comment (the Agent Card lifecycle)
# ════════════════════════════════════════════════════════════════════════
def make_card_handler(bindings: dict):
    dataset: AgentDataset = bindings["dataset"]
    events: EventBus = bindings["events"]

    def _register(payload: dict) -> dict:
        agent_id = payload.get("agent_id", "")
        if not agent_id:
            raise SocialError("register requires agent_id", code="bad_request")
        if dataset.load_card(agent_id) is not None and \
                not payload.get("overwrite"):
            raise DuplicateAgent(f"agent {agent_id!r} already registered",
                                 agent_id=agent_id)
        card = AgentCard(
            agent_id=agent_id,
            name=payload.get("name", agent_id),
            capacity=Capacity.from_dict(payload.get("capacity")),
            random_property=RandomProperty.from_dict(
                payload.get("random_property")),
            constraints=Constraints.from_dict(payload.get("constraints")),
            bio=payload.get("bio", ""),
        )
        card.vcl.append(f"{card.created}: registered")
        dataset.save_card(card)
        _emit(events, "agent_joined", agent_id, {"name": card.name})
        return {"ok": True, "card": card.to_dict()}

    def _get(payload: dict) -> dict:
        card = dataset.load_card(payload.get("agent_id", ""))
        if card is None:
            raise SocialError(f"unknown agent {payload.get('agent_id')!r}",
                              code="unknown_agent",
                              agent_id=payload.get("agent_id"))
        return {"ok": True, "card": card.to_dict()}

    def _list() -> dict:
        cards = sorted(dataset.list_cards(), key=lambda c: c.agent_id.lower())
        return {"ok": True, "cards": [c.to_dict() for c in cards]}

    def _comment(payload: dict) -> dict:
        target = payload.get("target_agent_id", "")
        card = dataset.load_card(target)
        if card is None:
            raise SocialError(f"unknown agent {target!r}",
                              code="unknown_agent", agent_id=target)
        author = payload.get("author_id", "")
        text = payload.get("text", "")
        if not text:
            raise SocialError("comment requires text", code="bad_request")
        card.add_comment(author, text)
        dataset.save_card(card)
        _emit(events, "card_commented", target,
              {"author_id": author, "comment": text[:200]})
        return {"ok": True, "card": card.to_dict()}

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "register":
                return _register(payload)
            if op == "get":
                return _get(payload)
            if op == "list":
                return _list()
            if op == "comment":
                return _comment(payload)
            raise SocialError(f"unknown card op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


# ════════════════════════════════════════════════════════════════════════
# profile — get / update_constraints (the three agent properties)
# ════════════════════════════════════════════════════════════════════════
def make_profile_handler(bindings: dict):
    dataset: AgentDataset = bindings["dataset"]
    events: EventBus = bindings["events"]

    def _get(payload: dict) -> dict:
        card = dataset.load_card(payload.get("agent_id", ""))
        if card is None:
            raise SocialError(f"unknown agent {payload.get('agent_id')!r}",
                              code="unknown_agent",
                              agent_id=payload.get("agent_id"))
        return {
            "ok": True,
            "agent_id": card.agent_id,
            "capacity": card.capacity.to_dict(),
            "random_property": card.random_property.to_dict(),
            "constraints": card.constraints.to_dict(),
            "status": card.status,
            "updated": card.updated,
        }

    def _update_constraints(payload: dict) -> dict:
        agent_id = payload.get("agent_id", "")
        card = dataset.load_card(agent_id)
        if card is None:
            raise SocialError(f"unknown agent {agent_id!r}",
                              code="unknown_agent", agent_id=agent_id)
        req = payload.get("constraints") or {}
        new_c = card.constraints.apply_update(
            agent_id, req.get("position"), req.get("resources"))
        card.constraints = new_c
        card.bump("constraints updated")
        dataset.save_card(card)
        _emit(events, "constraints_updated", agent_id,
              {"position": new_c.position, "resources": new_c.resources,
               "version": new_c.version})
        return {"ok": True, "constraints": new_c.to_dict(),
                "version": new_c.version}

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "get":
                return _get(payload)
            if op == "update_constraints":
                return _update_constraints(payload)
            raise SocialError(f"unknown profile op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


# ════════════════════════════════════════════════════════════════════════
# tasks — shared goal folders with individual task Markdown files
# ════════════════════════════════════════════════════════════════════════
def make_tasks_handler(bindings: dict):
    tasks: TaskManagement = bindings["tasks"]
    events: EventBus = bindings["events"]

    def _create_goal(payload: dict) -> dict:
        goal = tasks.create_goal(
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            owner_agent_id=payload.get("owner_agent_id", ""),
            goal_id=payload.get("goal_id"))
        _emit(events, "goal_created", goal.owner_agent_id,
              {"goal_id": goal.goal_id, "title": goal.title})
        return {"ok": True, "goal": goal.to_meta()}

    def _list_goals() -> dict:
        goals = []
        for g in sorted(tasks.list_goals(), key=lambda g: g.goal_id):
            meta = g.to_meta()
            meta["task_count"] = len(tasks.list_tasks(g.goal_id))
            goals.append(meta)
        return {"ok": True, "goals": goals}

    def _get_goal(payload: dict) -> dict:
        goal = tasks.get_goal(payload.get("goal_id", ""))
        out = goal.to_meta()
        out["tasks"] = [t.to_meta() for t in tasks.list_tasks(goal.goal_id)]
        return {"ok": True, "goal": out}

    def _delete_goal(payload: dict) -> dict:
        goal_id = payload.get("goal_id", "")
        tasks.delete_goal(goal_id)
        _emit(events, "goal_deleted", "portal", {"goal_id": goal_id})
        return {"ok": True, "deleted": goal_id}

    def _create_task(payload: dict) -> dict:
        task = tasks.create_task(
            goal_id=payload.get("goal_id", ""),
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            assignee_agent_id=payload.get("assignee_agent_id", ""),
            task_id=payload.get("task_id"),
            author_agent_id=payload.get("author_agent_id", ""),
            depends_on=payload.get("depends_on"),
            status=payload.get("status", "submitted"))
        _emit(events, "task_created", payload.get("author_agent_id", ""),
              {"goal_id": task.goal_id, "task_id": task.task_id,
               "title": task.title, "status": task.status})
        return {"ok": True, "task": task.to_meta()}

    def _update_task(payload: dict) -> dict:
        goal_id = payload.get("goal_id", "")
        task = tasks.update_task(
            goal_id=goal_id,
            task_id=payload.get("task_id", ""),
            agent_id=payload.get("author_agent_id", ""),
            status=payload.get("status"),
            note=payload.get("note"),
            assignee=payload.get("assignee_agent_id"))
        goal = tasks.get_goal(goal_id)
        if goal is not None:
            goal.bump()
            tasks.goals.save(goal)
        _emit(events, "task_updated", payload.get("author_agent_id", ""),
              {"goal_id": goal_id, "task_id": task.task_id,
               "status": task.status})
        return {"ok": True, "task": task.to_meta()}

    def _get_task(payload: dict) -> dict:
        task = tasks.get_task(payload.get("goal_id", ""),
                              payload.get("task_id", ""))
        return {"ok": True, "task": task.to_meta(),
                "notes": list(task.notes), "vcl": list(task.vcl)}

    def _list_tasks(payload: dict) -> dict:
        return {"ok": True, "tasks": [t.to_meta() for t in tasks.list_tasks(
            payload.get("goal_id", ""), payload.get("status"))]}

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "create_goal":
                return _create_goal(payload)
            if op == "list_goals":
                return _list_goals()
            if op == "get_goal":
                return _get_goal(payload)
            if op == "delete_goal":
                return _delete_goal(payload)
            if op == "create_task":
                return _create_task(payload)
            if op == "update_task":
                return _update_task(payload)
            if op == "get_task":
                return _get_task(payload)
            if op == "list_tasks":
                return _list_tasks(payload)
            raise SocialError(f"unknown tasks op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


# ════════════════════════════════════════════════════════════════════════
# chat_board — post / get / get_since / clear (the global chat board)
# ════════════════════════════════════════════════════════════════════════
def make_chat_board_handler(bindings: dict):
    chat = bindings["chat"]
    events: EventBus = bindings["events"]

    def _clear(payload: dict) -> dict:
        result = chat.clear(scope=payload.get("scope", "all"))
        _emit(events, "chat_cleared", "", result)
        return {"ok": True, **result}

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "post":
                result = chat.post(
                    author_agent_id=payload.get("author_agent_id", ""),
                    text=payload.get("text", ""),
                    tags=payload.get("tags"),
                    to_agent_id=payload.get("to_agent_id", ""))
                return {"ok": True, **result}
            if op == "get":
                return {"ok": True, "messages":
                        [m.to_dict() for m in chat.get(payload.get("limit"))]}
            if op == "get_since":
                return {"ok": True, "messages":
                        [m.to_dict() for m in
                         chat.get_since(int(payload.get("after_id", 0) or 0))]}
            if op == "clear":
                return _clear(payload)
            raise SocialError(f"unknown chat_board op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


# ════════════════════════════════════════════════════════════════════════
# events — the streaming channel (buffered or live)
# ════════════════════════════════════════════════════════════════════════
def make_events_handler(bindings: dict):
    events: EventBus = bindings["events"]

    def handler(payload: dict, context: dict) -> Any:
        since = int(payload.get("since", 0) or 0)
        live = bool(payload.get("live", False))
        timeout_s = float(payload.get("timeout_s", 0) or 0)
        if not live:
            events_list = events.since(since)
            return {
                "ok": True, "mode": "stream", "live": False,
                "events": [e.to_dict() for e in events_list],
                "cursor": events.last_seq(),
            }
        return events.stream(since=since, timeout_s=timeout_s)

    return handler


# ════════════════════════════════════════════════════════════════════════
# a2a — the four formal A2A interaction modes
# ════════════════════════════════════════════════════════════════════════
def make_a2a_handler(bindings: dict):
    ctx = bindings["a2a_ctx"]

    def handler(payload: dict, context: dict) -> Any:
        try:
            return execute_a2a(payload, ctx)
        except SocialError as exc:
            return exc.as_payload()

    return handler
