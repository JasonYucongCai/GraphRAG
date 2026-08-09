"""
agent_a1_tools.log_tools — Logging & Feedback tools (5 tools)

write_log, read_log, list_logs, write_feedback, read_feedback
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any
from .tool_base import EditTool, ReadOnlyTool, ToolContext, ToolResult


def _log_dir(ctx: ToolContext) -> Path:
    root = Path(ctx.workspace_root) if ctx.workspace_root else Path(".")
    return root / "recursive_agents" / "graph_data" / "logs"


def _feedback_dir(ctx: ToolContext) -> Path:
    root = Path(ctx.workspace_root) if ctx.workspace_root else Path(".")
    return root / "recursive_agents" / "feedback"


class WriteLogTool(EditTool):
    tool_name = "write_log"
    category = "log"
    description = "Write a log entry for an agent."
    tool_schema = {
        "type": "object", "required": ["agent_id", "message"],
        "properties": {
            "agent_id": {"type": "string"},
            "message": {"type": "string"},
            "level": {"type": "string", "description": "INFO, WARN, ERROR (default: INFO)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        message = args.get("message", "")
        level = args.get("level", "INFO")
        d = _log_dir(ctx)
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{stamp}] [{level}] [{agent_id}] {message}\n"
        log_file = d / f"{agent_id}.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
            return ToolResult.success(entry.strip(), agent_id=agent_id)
        except Exception as e:
            return ToolResult.fail(str(e))


class ReadLogTool(ReadOnlyTool):
    tool_name = "read_log"
    category = "log"
    description = "Read the log file for an agent."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string"},
            "tail_lines": {"type": "number", "description": "Number of recent lines (default: 50)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        tail = int(args.get("tail_lines", 50))
        log_file = _log_dir(ctx) / f"{agent_id}.log"
        if not log_file.exists():
            return ToolResult.success(f"(no log for {agent_id})", agent_id=agent_id)
        try:
            lines = log_file.read_text(encoding="utf-8").splitlines()
            recent = lines[-tail:] if len(lines) > tail else lines
            return ToolResult.success("\n".join(recent),
                                      agent_id=agent_id, total_lines=len(lines))
        except Exception as e:
            return ToolResult.fail(str(e))


class ListLogsTool(ReadOnlyTool):
    tool_name = "list_logs"
    category = "log"
    description = "List all available log files."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        d = _log_dir(ctx)
        if not d.exists():
            return ToolResult.success("(no logs directory)")
        logs = sorted(d.glob("*.log"))
        lines = [f"{lf.name} ({lf.stat().st_size} bytes)" for lf in logs]
        return ToolResult.success("\n".join(lines) if lines else "(no logs)",
                                  log_count=len(lines))


class WriteFeedbackTool(EditTool):
    tool_name = "write_feedback"
    category = "log"
    description = "Write structured feedback for an agent to the feedback directory."
    tool_schema = {
        "type": "object", "required": ["agent_id", "feedback"],
        "properties": {
            "agent_id": {"type": "string"},
            "feedback": {"type": "string", "description": "Feedback content."},
            "ok": {"type": "boolean", "description": "Whether the agent passed."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        feedback = args.get("feedback", "")
        ok = args.get("ok", True)
        d = _feedback_dir(ctx)
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        content = f"# {agent_id} feedback — {stamp}\nok: {ok}\n\n{feedback}\n"
        try:
            (d / f"{agent_id}.txt").write_text(content, encoding="utf-8")
            return ToolResult.success(f"Feedback written for {agent_id}",
                                      agent_id=agent_id, ok=ok)
        except Exception as e:
            return ToolResult.fail(str(e))


class ReadFeedbackTool(ReadOnlyTool):
    tool_name = "read_feedback"
    category = "log"
    description = "Read feedback for an agent from the feedback directory."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        fb_file = _feedback_dir(ctx) / f"{agent_id}.txt"
        if not fb_file.exists():
            return ToolResult.success(f"(no feedback for {agent_id})",
                                      agent_id=agent_id)
        try:
            content = fb_file.read_text(encoding="utf-8")
            return ToolResult.success(content, agent_id=agent_id)
        except Exception as e:
            return ToolResult.fail(str(e))


def register_log_tools(toolkit) -> None:
    toolkit.register_many([
        WriteLogTool(), ReadLogTool(), ListLogsTool(),
        WriteFeedbackTool(), ReadFeedbackTool(),
    ])
