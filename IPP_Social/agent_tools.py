"""
IPP_Social.agent_tools — the social tools every agent sees.

These tools make the ManyAgents agents DISCOVER the IPP_Social layer by
default: posting to the global chat board (with inter-agent addressing),
reading the board, discovering agent cards, creating/updating goal tasks,
and reading goals. They are registered into the SHARED ToolRegistry
(tools.api) and added to the codex_normal tool set, so every Codex agent
carries them.

Each tool reaches the social_activity node through the agent's own
``engine._social_node`` (the IPP node built by the platform) — invoked
through its guardrail envelope. Outside the platform (no social node)
the tools fail gracefully with a clear message.
"""
from __future__ import annotations

from typing import Optional

from tools.IPP import BaseTool, ToolContext, ToolResult

SOCIAL_TOOL_NAMES: list[str] = [
    "social_post",          # post to the chat board (to: chat_board|agents|<agent>)
    "social_board",         # read the chat board
    "social_agents",        # discover agent cards
    "social_goals",         # list goal folders
    "social_create_goal",   # create a shared goal
    "social_create_task",   # create a task inside a goal
    "social_update_task",   # update a task (status/note/assignee)
    "social_get_task",      # read one task (status/notes/VCL)
]

# addressing constants (mirror chat_board semantics)
TO_CHAT_BOARD = "chat_board"      # broadcast to the board
TO_AGENTS = "agents"              # addressed to every agent


def _social_node(ctx: ToolContext):
    """The agent's social_activity IPP node (bound by the platform)."""
    agent = getattr(ctx, "agent", None)
    return getattr(agent, "_social_node", None) if agent else None


def _invoke(ctx: ToolContext, channel: str, payload: dict):
    node = _social_node(ctx)
    if node is None:
        return ToolResult.fail(
            "social layer not connected — the agent is not bound to "
            "IPP_Social (run inside the Multi Agent platform)")
    try:
        result = node.invoke(channel, payload).payload
    except Exception as exc:  # noqa: BLE001 — structured errors
        return ToolResult.fail(f"social invoke failed: {exc}")
    if not isinstance(result, dict):
        return ToolResult.ok(str(result))
    if not result.get("ok"):
        return ToolResult.fail(result.get("error", "social op failed"))
    return ToolResult.ok(result)


class SocialPostTool(BaseTool):
    tool_name = "social_post"
    category = "social"
    description = (
        "Post a message to the global chat board (IPP_Social). "
        "to='chat_board' broadcasts to the board; to='agents' addresses "
        "every agent; to='<agent_id>' sends an inter-agent message to one "
        "agent (e.g. 'Codex_01_Alice').")
    tool_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string",
                        "description": "the message text"},
            "to": {"type": "string",
                   "description": "'chat_board' (default), 'agents', or a "
                                  "specific agent_id"},
        },
        "required": ["message"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = getattr(getattr(ctx, "agent", None), "name", "agent")
        return _invoke(ctx, "chat_board", {
            "op": "post", "author_agent_id": agent_id,
            "text": args["message"],
            "to_agent_id": args.get("to", TO_CHAT_BOARD)})


class SocialBoardTool(BaseTool):
    tool_name = "social_board"
    category = "social"
    description = "Read the global chat board (latest messages, with addressing)."
    tool_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "max messages"}},
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return _invoke(ctx, "chat_board", {"op": "get",
                                           "limit": args.get("limit", 30)})


class SocialAgentsTool(BaseTool):
    tool_name = "social_agents"
    category = "social"
    description = "Discover the agent cards on the social network (names, ids, capacity)."
    tool_schema = {"type": "object", "properties": {}}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return _invoke(ctx, "card", {"op": "list"})


class SocialGoalsTool(BaseTool):
    tool_name = "social_goals"
    category = "social"
    description = "List the shared goal folders in the social database."
    tool_schema = {"type": "object", "properties": {}}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return _invoke(ctx, "tasks", {"op": "list_goals"})


class SocialCreateGoalTool(BaseTool):
    tool_name = "social_create_goal"
    category = "social"
    description = "Create a shared goal folder (title + description) on the social network."
    tool_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["title"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = getattr(getattr(ctx, "agent", None), "name", "agent")
        return _invoke(ctx, "tasks", {
            "op": "create_goal", "title": args["title"],
            "description": args.get("description", ""),
            "owner_agent_id": agent_id})


class SocialCreateTaskTool(BaseTool):
    tool_name = "social_create_task"
    category = "social"
    description = "Create an individual task (Markdown file) inside a goal folder."
    tool_schema = {
        "type": "object",
        "properties": {
            "goal_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "assignee_agent_id": {"type": "string"},
        },
        "required": ["goal_id", "title"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = getattr(getattr(ctx, "agent", None), "name", "agent")
        return _invoke(ctx, "tasks", {
            "op": "create_task", "goal_id": args["goal_id"],
            "title": args["title"],
            "description": args.get("description", ""),
            "assignee_agent_id": args.get("assignee_agent_id", ""),
            "author_agent_id": agent_id})


class SocialUpdateTaskTool(BaseTool):
    tool_name = "social_update_task"
    category = "social"
    description = (
        "Update a collaborative task: status (submitted/processing/"
        "needs_input/completed/failed/canceled), note, or reassignment.")
    tool_schema = {
        "type": "object",
        "properties": {
            "goal_id": {"type": "string"},
            "task_id": {"type": "string"},
            "status": {"type": "string"},
            "note": {"type": "string"},
            "assignee_agent_id": {"type": "string"},
        },
        "required": ["goal_id", "task_id"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = getattr(getattr(ctx, "agent", None), "name", "agent")
        return _invoke(ctx, "tasks", {
            "op": "update_task", "goal_id": args["goal_id"],
            "task_id": args["task_id"],
            "author_agent_id": agent_id,
            "status": args.get("status"),
            "note": args.get("note"),
            "assignee_agent_id": args.get("assignee_agent_id")})


class SocialGetTaskTool(BaseTool):
    tool_name = "social_get_task"
    category = "social"
    description = "Read one task's current status, notes and Version Control Log."
    tool_schema = {
        "type": "object",
        "properties": {
            "goal_id": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["goal_id", "task_id"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return _invoke(ctx, "tasks", {"op": "get_task",
                                      "goal_id": args["goal_id"],
                                      "task_id": args["task_id"]})


SOCIAL_TOOLS: list[type[BaseTool]] = [
    SocialPostTool, SocialBoardTool, SocialAgentsTool, SocialGoalsTool,
    SocialCreateGoalTool, SocialCreateTaskTool, SocialUpdateTaskTool,
    SocialGetTaskTool,
]

_INSTANTIATED = False


def ensure_social_tools() -> None:
    """Idempotently register the social tools into the ToolRegistry."""
    global _INSTANTIATED
    if _INSTANTIATED:
        return
    for cls in SOCIAL_TOOLS:
        cls()
    _INSTANTIATED = True
