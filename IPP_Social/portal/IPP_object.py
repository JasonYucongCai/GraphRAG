"""
portal.IPP_object — the IPP Objects (Ω_k) of the social_portal node.

Handlers close over the shared GraphContext 𝒢, the SwarmManager and the
social_activity node (all bound in the GraphContext). External dispatch
respects the constructor-resolved topology: reads/writes to the social
network go through the social_activity node's guardrail envelope; agent
turns go through each agent's own engine node; the swarm channel only
starts agents whose engine node is a resolved downstream target.
"""
from __future__ import annotations

from typing import Any

from IPP_Social.errors import SocialError


def _err(exc: Exception) -> dict:
    if isinstance(exc, SocialError):
        return exc.as_payload()
    return {"ok": False, "error": "internal_error", "message": str(exc)}


# ════════════════════════════════════════════════════════════════════════
# discover — agents / goals / cards / status
# ════════════════════════════════════════════════════════════════════════
def make_discover_handler(bindings: dict):
    social_node = bindings["social_node"]
    swarm = bindings["swarm"]

    def _agents() -> dict:
        cards = social_node.invoke("card", {"op": "list"}).payload
        addresses = swarm.agent_addresses()
        out = []
        for card in (cards.get("cards") or []):
            agent_id = card.get("agent_id")
            if agent_id in ("user", "portal"):
                continue   # the operator/portal cards are not agents
            addr = addresses.get(agent_id, {})
            out.append({
                "agent_id": agent_id,
                "name": card.get("name"),
                "bio": card.get("bio", ""),
                "status": addr.get("status", "offline"),
                "engine_node": addr.get("engine_node", ""),
                "tools_node": addr.get("tools_node", ""),
                "in_topology": addr.get("in_topology", False),
                "runs_completed": addr.get("runs_completed", 0),
                "last_activity": addr.get("last_activity", ""),
                "capacity_top3": _top3(card.get("capacity") or {}),
            })
        return {"ok": True, "agents": out}

    def _goals() -> dict:
        goals = social_node.invoke("tasks", {"op": "list_goals"}).payload
        return {"ok": True, "goals": goals.get("goals", [])}

    def _cards() -> dict:
        cards = social_node.invoke("card", {"op": "list"}).payload
        return {"ok": True, "cards": cards.get("cards", [])}

    def _status() -> dict:
        return {"ok": True, "status": swarm.status()}

    def _board() -> dict:
        msgs = social_node.invoke("chat_board", {"op": "get"}).payload
        return {"ok": True, "messages": msgs.get("messages", [])}

    def _goal_detail(payload: dict) -> dict:
        detail = social_node.invoke("tasks", {"op": "get_goal",
                                               "goal_id": payload.get("goal_id", "")}).payload
        return detail

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "agents":
                return _agents()
            if op == "goals":
                return _goals()
            if op == "cards":
                return _cards()
            if op == "status":
                return _status()
            if op == "board":
                return _board()
            if op == "goal_detail":
                return _goal_detail(payload)
            raise SocialError(f"unknown discover op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


def _top3(capacity: dict) -> list[dict]:
    return [{"dimension": d, "score": round(float(capacity[d]), 1)}
            for d in sorted(capacity, key=capacity.get, reverse=True)[:3]]


# ════════════════════════════════════════════════════════════════════════
# command — goal / task / instruct / board / goals
# ════════════════════════════════════════════════════════════════════════
def make_command_handler(bindings: dict):
    social_node = bindings["social_node"]
    swarm = bindings["swarm"]

    def _goal(payload: dict) -> dict:
        return social_node.invoke("tasks", {
            "op": "create_goal", "title": payload.get("title", ""),
            "description": payload.get("description", "")}).payload

    def _task(payload: dict) -> dict:
        return social_node.invoke("tasks", {
            "op": "create_task", "goal_id": payload.get("goal_id", ""),
            "title": payload.get("title", ""),
            "description": payload.get("description", ""),
            "assignee_agent_id": payload.get("agent_id", ""),
            "author_agent_id": "portal"}).payload

    def _instruct(payload: dict) -> dict:
        return swarm.instruct(
            agent_id=payload.get("agent_id", ""),
            instruction=payload.get("instruction", ""),
            goal_id=payload.get("goal_id"))

    def _board(payload: dict) -> dict:
        return social_node.invoke("chat_board", {
            "op": "post",
            "author_agent_id": payload.get("author_agent_id", ""),
            "text": payload.get("text", ""),
            "tags": payload.get("tags"),
            "to_agent_id": payload.get("to_agent_id", "")}).payload

    def _goals() -> dict:
        return social_node.invoke("tasks", {"op": "list_goals"}).payload

    def _delete_goal(payload: dict) -> dict:
        return social_node.invoke("tasks", {"op": "delete_goal",
                                            "goal_id": payload.get("goal_id", "")}).payload

    def _clear_chat(payload: dict) -> dict:
        return social_node.invoke("chat_board", {"op": "clear",
                                                 "scope": payload.get("scope", "all")}).payload

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "goal":
                return _goal(payload)
            if op == "task":
                return _task(payload)
            if op == "instruct":
                return _instruct(payload)
            if op == "board":
                return _board(payload)
            if op == "goals":
                return _goals()
            if op == "delete_goal":
                return _delete_goal(payload)
            if op == "clear_chat":
                return _clear_chat(payload)
            raise SocialError(f"unknown command op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


# ════════════════════════════════════════════════════════════════════════
# monitor — live swarm activity (buffered or live iterator)
# ════════════════════════════════════════════════════════════════════════
def make_monitor_handler(bindings: dict):
    swarm = bindings["swarm"]

    def handler(payload: dict, context: dict) -> Any:
        since = int(payload.get("since", 0) or 0)
        live = bool(payload.get("live", False))
        timeout_s = float(payload.get("timeout_s", 0) or 0)
        if not live:
            return {"ok": True, "mode": "stream", "live": False,
                    "events": swarm.bus.since(since),
                    "cursor": swarm.bus.last_seq()}
        return swarm.bus.iter_live(since=since, timeout_s=timeout_s)

    return handler


# ════════════════════════════════════════════════════════════════════════
# swarm — start / stop / status / addresses (the concurrent team)
# ════════════════════════════════════════════════════════════════════════
def make_swarm_handler(bindings: dict):
    swarm = bindings["swarm"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "start":
                return swarm.start(
                    goal_title=payload.get("goal", ""),
                    instructions=payload.get("instructions", ""),
                    agent_ids=payload.get("agent_ids"),
                    goal_id=payload.get("goal_id"))
            if op == "stop":
                return swarm.stop()
            if op == "status":
                return {"ok": True, "status": swarm.status()}
            if op == "addresses":
                return {"ok": True, "addresses": swarm.agent_addresses()}
            raise SocialError(f"unknown swarm op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler


# ════════════════════════════════════════════════════════════════════════
# settings — get / set (the Multi Agent platform settings)
# ════════════════════════════════════════════════════════════════════════
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
            raise SocialError(f"unknown settings op {op!r}",
                              code="bad_request", op=op)
        except SocialError as exc:
            return exc.as_payload()

    return handler
