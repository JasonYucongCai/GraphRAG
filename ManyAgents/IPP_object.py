"""
ManyAgents.IPP_object — the IPP Objects (Ω_k) of the many_agents node.

Two channels in one unified node. Every handler is self-contained — no
delegation to sub-folders, no construct.py singletons.

  • cards       — agent card CRUD (list/get/save/delete/comment/provision)
  • orchestrate — swarm lifecycle (start/stop/instruct/status/…)

Γ (the Constructor) binds dataset + swarm into the GraphContext before
construction. Ω and Ξ run independently thereafter.
"""
from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════════
# cards channel — agent card CRUD over the AgentDataset
# ═══════════════════════════════════════════════════════════════════════════
def make_cards_handler(bindings: dict):
    ds = bindings["dataset"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "list":
                cards = ds.list_cards()
                return {"ok": True, "data": {
                    "cards": [c.to_dict() for c in cards], "count": len(cards)}}
            if op == "get":
                card = ds.load_card(payload.get("agent_id", ""))
                if card is None:
                    return {"ok": False, "error": "not_found",
                            "message": f"no card for {payload.get('agent_id')!r}"}
                return {"ok": True, "data": {"card": card.to_dict()}}
            if op == "save":
                from ManyAgents.agent_management.agent_card import AgentCard
                card = AgentCard.from_dict(payload.get("card", {}))
                ds.save_card(card)
                return {"ok": True, "data": {"card": card.to_dict(), "saved": True}}
            if op == "delete":
                agent_id = payload.get("agent_id", "")
                path = ds.card_path(agent_id)
                if path.exists():
                    path.unlink()
                    return {"ok": True, "data": {"deleted": agent_id}}
                return {"ok": False, "error": "not_found"}
            if op == "comment":
                card = ds.load_card(payload.get("agent_id", ""))
                if card is None:
                    return {"ok": False, "error": "not_found"}
                card.add_comment(payload.get("author_id", "unknown"),
                                 payload.get("text", ""))
                ds.save_card(card)
                return {"ok": True, "data": {"card": card.to_dict()}}
            if op == "provision":
                from IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision import provision_many_agents
                provision_many_agents(ds)
                return {"ok": True, "data": {"provisioned": True, "count": len(ds.list_cards())}}
            return {"ok": False, "error": "bad_request", "message": f"unknown cards op {op!r}"}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# orchestrate channel — swarm lifecycle (start/stop/instruct/status/…)
# ═══════════════════════════════════════════════════════════════════════════
def make_orchestrate_handler(bindings: dict):
    swarm = bindings["swarm"]

    def handler(payload: dict, context: dict) -> dict:
        try:
            op = payload.get("op")
            if op == "start":
                r = swarm.start(goal_title=payload.get("goal_title", ""),
                                instructions=payload.get("instructions", ""),
                                agent_ids=payload.get("agent_ids"),
                                goal_id=payload.get("goal_id"))
                return {"ok": True, "data": r}
            if op == "stop":
                swarm.stop_responder(); swarm.stop()
                return {"ok": True, "data": swarm.status()}
            if op == "instruct":
                r = swarm.instruct(agent_id=payload.get("agent_id", ""),
                                   instruction=payload.get("instructions", ""),
                                   goal_id=payload.get("goal_id"))
                return {"ok": True, "data": r}
            if op == "status":
                return {"ok": True, "data": swarm.status()}
            if op == "apply_settings":
                swarm.apply_settings()
                return {"ok": True, "data": swarm.status()}
            if op == "responder_start":
                swarm.start_responder()
                return {"ok": True, "message": "responder started"}
            if op == "responder_stop":
                swarm.stop_responder()
                return {"ok": True, "message": "responder stopped"}
            return {"ok": False, "error": "bad_request", "message": f"unknown op {op!r}"}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    return handler
