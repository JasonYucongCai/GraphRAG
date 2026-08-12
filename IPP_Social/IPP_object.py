"""
IPP_Social.IPP_object — the IPP Objects (Ω_k) of the social node.

Eleven channels in one unified node. Every handler is self-contained with
all its logic inline. Handlers resolve their dependencies from bindings
(dataset, tasks, chat, events, push, a2a_ctx, swarm, settings) which are
bound by Γ (the Constructor) into the GraphContext before construction.

Social layer channels (6):
  card, profile, tasks, chat_board, events, a2a

Portal layer channels (5):
  discover, command, monitor, swarm, settings
"""
from __future__ import annotations

from typing import Any

from IPP_Social.errors import DuplicateAgent, SocialError
from ManyAgents.agent_management.agent_card import AgentCard
from ManyAgents.agent_management.capacity import Capacity
from ManyAgents.agent_management.constraints import Constraints
from ManyAgents.agent_management.random_property import RandomProperty


# ═══════════════════════════════════════════════════════════════════════════
# card — agent registration / discovery / comments
# ═══════════════════════════════════════════════════════════════════════════
def make_card_handler(bindings: dict):
    dataset = bindings["dataset"]
    events = bindings["events"]

    def _emit(type_, agent_id="", payload=None):
        events.append(type_, agent_id, payload)

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "register":
                agent_id = payload.get("agent_id", "")
                if not agent_id:
                    raise SocialError("register requires agent_id", code="bad_request")
                if dataset.load_card(agent_id) is not None and not payload.get("overwrite"):
                    raise DuplicateAgent(f"agent {agent_id!r} already registered", agent_id=agent_id)
                card = AgentCard(
                    agent_id=agent_id, name=payload.get("name", agent_id),
                    capacity=Capacity.from_dict(payload.get("capacity")),
                    random_property=RandomProperty.from_dict(payload.get("random_property")),
                    constraints=Constraints.from_dict(payload.get("constraints")),
                    bio=payload.get("bio", ""))
                card.vcl.append(f"{card.created}: registered")
                dataset.save_card(card)
                _emit("agent_joined", agent_id, {"name": card.name})
                return {"ok": True, "card": card.to_dict()}
            if op == "get":
                card = dataset.load_card(payload.get("agent_id", ""))
                if card is None:
                    raise SocialError(f"unknown agent {payload.get('agent_id')!r}", code="unknown_agent")
                return {"ok": True, "card": card.to_dict()}
            if op == "list":
                cards = sorted(dataset.list_cards(), key=lambda c: c.agent_id.lower())
                return {"ok": True, "cards": [c.to_dict() for c in cards]}
            if op == "comment":
                target = payload.get("target_agent_id", "")
                card = dataset.load_card(target)
                if card is None:
                    raise SocialError(f"unknown agent {target!r}", code="unknown_agent", agent_id=target)
                text = payload.get("text", "")
                if not text:
                    raise SocialError("comment requires text", code="bad_request")
                card.add_comment(payload.get("author_id", ""), text)
                dataset.save_card(card)
                _emit("card_commented", target, {"author_id": payload.get("author_id", ""), "comment": text[:200]})
                return {"ok": True, "card": card.to_dict()}
            raise SocialError(f"unknown card op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# profile — read/update the three agent properties
# ═══════════════════════════════════════════════════════════════════════════
def make_profile_handler(bindings: dict):
    dataset = bindings["dataset"]
    events = bindings["events"]

    def _emit(type_, agent_id="", payload=None):
        events.append(type_, agent_id, payload)

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            agent_id = payload.get("agent_id", "")
            card = dataset.load_card(agent_id)
            if card is None:
                raise SocialError(f"unknown agent {agent_id!r}", code="unknown_agent", agent_id=agent_id)
            if op == "get":
                return {"ok": True, "agent_id": card.agent_id,
                        "capacity": card.capacity.to_dict(),
                        "random_property": card.random_property.to_dict(),
                        "constraints": card.constraints.to_dict(),
                        "status": card.status, "updated": card.updated}
            if op == "update_constraints":
                req = payload.get("constraints") or {}
                new_c = card.constraints.apply_update(agent_id, req.get("position"), req.get("resources"))
                card.constraints = new_c
                card.bump("constraints updated")
                dataset.save_card(card)
                _emit("constraints_updated", agent_id, {"position": new_c.position, "resources": new_c.resources, "version": new_c.version})
                return {"ok": True, "constraints": new_c.to_dict(), "version": new_c.version}
            raise SocialError(f"unknown profile op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# tasks — shared goal folders + individual task Markdown files
# ═══════════════════════════════════════════════════════════════════════════
def make_tasks_handler(bindings: dict):
    tasks_mgr = bindings["tasks"]
    events = bindings["events"]

    def _emit(type_, agent_id="", payload=None):
        events.append(type_, agent_id, payload)

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "create_goal":
                goal = tasks_mgr.create_goal(title=payload.get("title", ""), description=payload.get("description", ""),
                                             owner_agent_id=payload.get("owner_agent_id", ""), goal_id=payload.get("goal_id"))
                _emit("goal_created", goal.owner_agent_id, {"goal_id": goal.goal_id, "title": goal.title})
                return {"ok": True, "goal": goal.to_meta()}
            if op == "list_goals":
                goals = []
                for g in sorted(tasks_mgr.list_goals(), key=lambda g: g.goal_id):
                    meta = g.to_meta(); meta["task_count"] = len(tasks_mgr.list_tasks(g.goal_id)); goals.append(meta)
                return {"ok": True, "goals": goals}
            if op == "get_goal":
                goal = tasks_mgr.get_goal(payload.get("goal_id", ""))
                out = goal.to_meta(); out["tasks"] = [t.to_meta() for t in tasks_mgr.list_tasks(goal.goal_id)]
                return {"ok": True, "goal": out}
            if op == "delete_goal":
                gid = payload.get("goal_id", ""); tasks_mgr.delete_goal(gid)
                _emit("goal_deleted", "portal", {"goal_id": gid}); return {"ok": True, "deleted": gid}
            if op == "create_task":
                task = tasks_mgr.create_task(goal_id=payload.get("goal_id", ""), title=payload.get("title", ""),
                                             description=payload.get("description", ""), assignee_agent_id=payload.get("assignee_agent_id", ""),
                                             task_id=payload.get("task_id"), author_agent_id=payload.get("author_agent_id", ""),
                                             depends_on=payload.get("depends_on"), status=payload.get("status", "submitted"))
                _emit("task_created", payload.get("author_agent_id", ""), {"goal_id": task.goal_id, "task_id": task.task_id, "title": task.title, "status": task.status})
                return {"ok": True, "task": task.to_meta()}
            if op == "update_task":
                goal_id = payload.get("goal_id", ""); task = tasks_mgr.update_task(
                    goal_id=goal_id, task_id=payload.get("task_id", ""), agent_id=payload.get("author_agent_id", ""),
                    status=payload.get("status"), note=payload.get("note"), assignee=payload.get("assignee_agent_id"))
                goal = tasks_mgr.get_goal(goal_id)
                if goal is not None: goal.bump(); tasks_mgr.goals.save(goal)
                _emit("task_updated", payload.get("author_agent_id", ""), {"goal_id": goal_id, "task_id": task.task_id, "status": task.status})
                return {"ok": True, "task": task.to_meta()}
            if op == "get_task":
                task = tasks_mgr.get_task(payload.get("goal_id", ""), payload.get("task_id", ""))
                return {"ok": True, "task": task.to_meta(), "notes": list(task.notes), "vcl": list(task.vcl)}
            if op == "list_tasks":
                return {"ok": True, "tasks": [t.to_meta() for t in tasks_mgr.list_tasks(payload.get("goal_id", ""), payload.get("status"))]}
            raise SocialError(f"unknown tasks op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# chat_board — global chat board with addressing
# ═══════════════════════════════════════════════════════════════════════════
def make_chat_board_handler(bindings: dict):
    chat = bindings["chat"]
    events = bindings["events"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            clean = {k: v for k, v in payload.items() if v is not None}
            op = clean.get("op")
            if op == "post":
                r = chat.post(author_agent_id=clean.get("author_agent_id", ""), text=clean.get("text", ""),
                              tags=clean.get("tags"), to_agent_id=clean.get("to_agent_id", ""))
                return {"ok": True, **r}
            if op == "get":
                return {"ok": True, "messages": [m.to_dict() for m in chat.get(clean.get("limit"))]}
            if op == "get_since":
                return {"ok": True, "messages": [m.to_dict() for m in chat.get_since(int(clean.get("after_id", 0) or 0))]}
            if op == "clear":
                r = chat.clear(scope=clean.get("scope", "all")); events.append("chat_cleared", "", r)
                return {"ok": True, **r}
            raise SocialError(f"unknown chat_board op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# events — streaming event bus (buffered or live)
# ═══════════════════════════════════════════════════════════════════════════
def make_events_handler(bindings: dict):
    events = bindings["events"]

    def handler(payload: dict, context: dict) -> Any:
        since = int(payload.get("since", 0) or 0)
        live = bool(payload.get("live", False))
        timeout_s = float(payload.get("timeout_s", 0) or 0)
        if not live:
            ev_list = events.since(since)
            return {"ok": True, "mode": "stream", "live": False,
                    "events": [e.to_dict() for e in ev_list], "cursor": events.last_seq()}
        return events.stream(since=since, timeout_s=timeout_s)
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# a2a — the four formal A2A interaction modes
# ═══════════════════════════════════════════════════════════════════════════
def make_a2a_handler(bindings: dict):
    from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_modes import execute_a2a
    ctx = bindings["a2a_ctx"]

    def handler(payload: dict, context: dict) -> Any:
        try:
            return execute_a2a(payload, ctx)
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# PORTAL LAYER (5 channels)
# ═══════════════════════════════════════════════════════════════════════════

def _top3(capacity: dict) -> list[dict]:
    return [{"dimension": d, "score": round(float(capacity[d]), 1)}
            for d in sorted(capacity, key=capacity.get, reverse=True)[:3]]


# ── discover ────────────────────────────────────────────────────────────────
def make_discover_handler(bindings: dict):
    dataset = bindings["dataset"]
    tasks_mgr = bindings["tasks"]
    swarm = bindings["swarm"]
    chat = bindings["chat"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "agents":
                cards = dataset.list_cards()
                addresses = swarm.agent_addresses()
                out = []
                for card in cards:
                    agent_id = card.agent_id
                    if agent_id in ("user", "portal"):
                        continue
                    addr = addresses.get(agent_id, {})
                    out.append({"agent_id": agent_id, "name": card.name, "bio": card.bio,
                                "status": addr.get("status", "offline"),
                                "engine_node": addr.get("engine_node", ""),
                                "tools_node": addr.get("tools_node", ""),
                                "in_topology": addr.get("in_topology", False),
                                "runs_completed": addr.get("runs_completed", 0),
                                "last_activity": addr.get("last_activity", ""),
                                "capacity_top3": _top3(card.capacity.to_dict())})
                return {"ok": True, "agents": out}
            if op == "goals":
                goals = []
                for g in sorted(tasks_mgr.list_goals(), key=lambda g: g.goal_id):
                    meta = g.to_meta(); meta["task_count"] = len(tasks_mgr.list_tasks(g.goal_id)); goals.append(meta)
                return {"ok": True, "goals": goals}
            if op == "cards":
                cards = sorted(dataset.list_cards(), key=lambda c: c.agent_id.lower())
                return {"ok": True, "cards": [c.to_dict() for c in cards]}
            if op == "status":
                return {"ok": True, "status": swarm.status()}
            if op == "board":
                msgs = chat.get(None)
                return {"ok": True, "messages": [m.to_dict() for m in msgs]}
            if op == "goal_detail":
                goal = tasks_mgr.get_goal(payload.get("goal_id", ""))
                out = goal.to_meta(); out["tasks"] = [t.to_meta() for t in tasks_mgr.list_tasks(goal.goal_id)]
                return out
            raise SocialError(f"unknown discover op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ── command ─────────────────────────────────────────────────────────────────
def make_command_handler(bindings: dict):
    tasks_mgr = bindings["tasks"]
    swarm = bindings["swarm"]
    chat = bindings["chat"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "goal":
                goal = tasks_mgr.create_goal(title=payload.get("title", ""), description=payload.get("description", ""))
                return {"ok": True, "goal": goal.to_meta()}
            if op == "task":
                task = tasks_mgr.create_task(goal_id=payload.get("goal_id", ""), title=payload.get("title", ""),
                                             description=payload.get("description", ""),
                                             assignee_agent_id=payload.get("agent_id", ""), author_agent_id="portal")
                return {"ok": True, "task": task.to_meta()}
            if op == "instruct":
                return swarm.instruct(agent_id=payload.get("agent_id", ""),
                                      instruction=payload.get("instruction", ""), goal_id=payload.get("goal_id"))
            if op == "board":
                post_payload = {"op": "post", "author_agent_id": payload.get("author_agent_id", ""),
                                "text": payload.get("text", ""), "to_agent_id": payload.get("to_agent_id", "")}
                tags = payload.get("tags")
                if tags is not None: post_payload["tags"] = tags
                r = chat.post(**{k: v for k, v in post_payload.items() if k != "op"})
                return {"ok": True, **r}
            if op == "goals":
                goals = []
                for g in sorted(tasks_mgr.list_goals(), key=lambda g: g.goal_id):
                    meta = g.to_meta(); meta["task_count"] = len(tasks_mgr.list_tasks(g.goal_id)); goals.append(meta)
                return {"ok": True, "goals": goals}
            if op == "delete_goal":
                tasks_mgr.delete_goal(payload.get("goal_id", ""))
                return {"ok": True, "deleted": payload.get("goal_id", "")}
            if op == "clear_chat":
                r = chat.clear(scope=payload.get("scope", "all"))
                return {"ok": True, **r}
            raise SocialError(f"unknown command op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ── monitor ─────────────────────────────────────────────────────────────────
def make_monitor_handler(bindings: dict):
    swarm = bindings["swarm"]

    def handler(payload: dict, context: dict) -> Any:
        since = int(payload.get("since", 0) or 0)
        live = bool(payload.get("live", False))
        timeout_s = float(payload.get("timeout_s", 0) or 0)
        if not live:
            return {"ok": True, "mode": "stream", "live": False,
                    "events": swarm.bus.since(since), "cursor": swarm.bus.last_seq()}
        return swarm.bus.iter_live(since=since, timeout_s=timeout_s)
    return handler


# ── swarm ───────────────────────────────────────────────────────────────────
def make_swarm_handler(bindings: dict):
    swarm = bindings["swarm"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "start":
                return swarm.start(goal_title=payload.get("goal", ""), instructions=payload.get("instructions", ""),
                                   agent_ids=payload.get("agent_ids"), goal_id=payload.get("goal_id"))
            if op == "stop":
                return swarm.stop()
            if op == "status":
                return {"ok": True, "status": swarm.status()}
            if op == "addresses":
                return {"ok": True, "addresses": swarm.agent_addresses()}
            raise SocialError(f"unknown swarm op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler


# ── settings ────────────────────────────────────────────────────────────────
def make_settings_handler(bindings: dict):
    settings = bindings["settings"]
    swarm = bindings["swarm"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "get":
                return {"ok": True, "settings": settings.all()}
            if op == "set":
                updated = settings.update(payload.get("settings") or {})
                swarm.apply_settings()
                return {"ok": True, "settings": updated}
            raise SocialError(f"unknown settings op {op!r}", code="bad_request")
        except SocialError as exc:
            return exc.as_payload()
    return handler
