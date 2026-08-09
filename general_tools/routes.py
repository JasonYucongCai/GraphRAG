"""
tools.routes — the invoke channel's routing table (R*_k).

Every agent-callable tool name maps to a target channel's guardrail
envelope:

  ("self", channel, op)        — a channel of the tools node itself
                                 (codex channels: op=None → the args are the
                                 channel payload)
  ("database", channel, op)    — the database node (external target)
  ("social_activity", ch, op)  — the social node (external target)

This table is executor state (τ*_k routing, §3.4): the invoke channel's
handler resolves a name through it and invokes the target's envelope.
The F-file channel input schemas (anyOf per-op branches) ARE the tool
definitions — see tools/catalog.py.
"""
from __future__ import annotations

# ── the 19 codex channels of the tools node itself ──────────────────────────
CODEX_CHANNELS = [
    "shell_command", "read_file", "write_file", "list_directory",
    "search_files", "grep_search", "apply_patch", "view_image",
    "current_time", "plan", "request_user_input", "spawn_agent",
    "wait_agent", "list_agents", "cancel_agent", "send_notification",
    "memory_read", "memory_write", "web_search",
]

# ── graph / encoder / build / check ops (tools node channels) ───────────────
GRAPH_OPS = {
    "get_local_graph": "local",
    "read_node": "read",
    "validate_graph": "validate",
    "summarize_local": "summarize",
}
ENCODER_OPS = {"search_nodes": "search_nodes"}
CHECK_OPS = {
    "review_top_threats": "review",
    "standard_check": "standard",
    "advanced_check": "advanced",
}

# ── database node (external) ────────────────────────────────────────────────
DATABASE_ROUTES = {
    "create_project": ("project", "create"),
    "open_project": ("project", "open"),
    "list_projects": ("project", "list"),
    "project_info": ("project", "info"),
    "register_node": ("nodes", "register"),
    "update_node": ("nodes", "update"),
    "delete_node": ("nodes", "delete"),
    "add_reference": ("nodes", "reference"),
    "append_vcl": ("nodes", "vcl"),
    "link_nodes": ("edges", "link"),
    "unlink": ("edges", "unlink"),
    "infer_edges": ("edges", "infer"),
    "probe_gap": ("edges", "probe"),
    "save_graph": ("graph", "save"),
    "export_interactive": ("graph", "export_interactive"),
    "sync_project": ("graph", "sync"),
    "list_supplements": ("supplement", "list"),
    "create_supplement": ("supplement", "create"),
    "open_supplement": ("supplement", "open"),
    "close_supplement": ("supplement", "close"),
    "sync_supplement": ("supplement", "sync"),
    "save_supplement_graph": ("supplement", "save_graph"),
    "add_supplement_asset": ("supplement", "add_asset"),
    "get_categories": ("categories", "get"),
    "update_categories": ("categories", "update"),
}

# ── social_activity node (external; payload adapters) ───────────────────────
def _social_post(args: dict, meta: dict) -> dict:
    result = {
        "op": "post",
        "author_agent_id": (meta.get("agent_id")
                            or args.get("author_agent_id", "")
                            or "agent"),
        "text": args.get("text") or args.get("message", ""),
        "to_agent_id": (args.get("to_agent_id")
                        or args.get("to", "chat_board")),
    }
    tags = args.get("tags")
    if tags is not None:
        result["tags"] = tags
    return result


def _social_board(args: dict, meta: dict) -> dict:
    return {"op": "get", "limit": args.get("limit", 200)}


def _social_agents(args: dict, meta: dict) -> dict:
    return {"op": "list"}


def _social_goals(args: dict, meta: dict) -> dict:
    return {"op": "list_goals"}


def _social_create_goal(args: dict, meta: dict) -> dict:
    return {"op": "create_goal", "title": args.get("title", ""),
            "description": args.get("description", ""),
            "goal_id": args.get("goal_id", ""),
            "owner_agent_id": meta.get("agent_id") or "agent"}


def _social_create_task(args: dict, meta: dict) -> dict:
    return {"op": "create_task", "goal_id": args.get("goal_id", ""),
            "title": args.get("title", ""),
            "description": args.get("description", ""),
            "task_id": args.get("task_id", ""),
            "assignee_agent_id": args.get("assignee_agent_id", ""),
            "author_agent_id": meta.get("agent_id") or "agent",
            "status": args.get("status")}


def _social_update_task(args: dict, meta: dict) -> dict:
    return {"op": "update_task", "goal_id": args.get("goal_id", ""),
            "task_id": args.get("task_id", ""),
            "author_agent_id": meta.get("agent_id") or "agent",
            "status": args.get("status"),
            "note": args.get("note"),
            "assignee_agent_id": args.get("assignee_agent_id", "")}


def _social_get_task(args: dict, meta: dict) -> dict:
    return {"op": "get_task", "goal_id": args.get("goal_id", ""),
            "task_id": args.get("task_id", "")}


def _social_inbox(args: dict, meta: dict) -> dict:
    return {"mode": "push", "action": "inbox",
            "agent_id": meta.get("agent_id") or args.get("agent_id", "")}


SOCIAL_ROUTES = {
    "social_post": ("chat_board", "post", _social_post),
    "social_board": ("chat_board", "get", _social_board),
    "social_agents": ("card", "list", _social_agents),
    "social_goals": ("tasks", "list_goals", _social_goals),
    "social_create_goal": ("tasks", "create_goal", _social_create_goal),
    "social_create_task": ("tasks", "create_task", _social_create_task),
    "social_update_task": ("tasks", "update_task", _social_update_task),
    "social_get_task": ("tasks", "get_task", _social_get_task),
    "social_inbox": ("a2a", "push", _social_inbox),
}


# ── the full name → route map ───────────────────────────────────────────────
def build_routes() -> dict:
    """{tool_name: route} — route = ("self"|"database"|"social_activity",
    channel, op|None, adapter|None)."""
    routes: dict = {}
    for name in CODEX_CHANNELS:
        routes[name] = ("self", name, None, None)
    for name, op in GRAPH_OPS.items():
        routes[name] = ("self", "graph", op, None)
    for name, op in ENCODER_OPS.items():
        routes[name] = ("self", "encoder", op, None)
    for name, op in CHECK_OPS.items():
        routes[name] = ("self", "check", op, None)
    for name, (channel, op) in DATABASE_ROUTES.items():
        routes[name] = ("database", channel, op, None)
    for name, (channel, op, adapter) in SOCIAL_ROUTES.items():
        routes[name] = ("social_activity", channel, op, adapter)
    return routes


ROUTES: dict = build_routes()
