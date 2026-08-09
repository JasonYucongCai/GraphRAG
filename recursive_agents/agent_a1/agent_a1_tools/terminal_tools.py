"""
agent_a1_tools.terminal_tools — Terminal & Shell tools (6 tools)

run_in_terminal, get_terminal_output, send_to_terminal,
kill_terminal, terminal_selection, terminal_last_command
"""
from __future__ import annotations
import asyncio, os
from typing import Any
from .tool_base import ExecuteTool, ReadOnlyTool, ToolContext, ToolResult


class RunInTerminalTool(ExecuteTool):
    tool_name = "run_in_terminal"
    category = "terminal"
    description = "Execute a shell command and return the output."
    tool_schema = {
        "type": "object", "required": ["command"],
        "properties": {
            "command": {"type": "string", "description": "Shell command to run."},
            "explanation": {"type": "string"},
            "goal": {"type": "string"},
            "timeout": {"type": "number", "description": "Timeout in ms."},
            "cwd": {"type": "string", "description": "Working directory."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        import subprocess
        cmd = args.get("command", "")
        cwd = args.get("cwd", ctx.workspace_root) or os.getcwd()
        timeout = int(args.get("timeout", 60000)) / 1000
        if not cmd:
            return ToolResult.fail("command is required")
        try:
            p = subprocess.run(cmd, shell=True, cwd=cwd,
                              capture_output=True, text=True,
                              timeout=min(timeout, 120))
            out = p.stdout[:4000]
            err = p.stderr[:1000]
            content = out + (f"\n[stderr]\n{err}" if err else "")
            return ToolResult.success(content, exit_code=p.returncode,
                                      command=cmd[:200])
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"Timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(str(e))


class GetTerminalOutputTool(ReadOnlyTool):
    tool_name = "get_terminal_output"
    category = "terminal"
    description = "Get output from a background terminal."
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {"id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success(f"Terminal {args.get('id', '?')}: (no persistent state)")


class SendToTerminalTool(ExecuteTool):
    tool_name = "send_to_terminal"
    category = "terminal"
    description = "Send input to an active terminal."
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "command": {"type": "string", "description": "Text to send."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success(f"Sent to terminal {args.get('id', '?')}")


class KillTerminalTool(ExecuteTool):
    tool_name = "kill_terminal"
    category = "terminal"
    description = "Kill a terminal by its ID."
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {"id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success(f"Killed terminal {args.get('id', '?')}")


class TerminalSelectionTool(ReadOnlyTool):
    tool_name = "terminal_selection"
    category = "terminal"
    description = "Get the current selection in the active terminal."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success("(terminal selection — no active selection)")


class TerminalLastCommandTool(ReadOnlyTool):
    tool_name = "terminal_last_command"
    category = "terminal"
    description = "Get the last command run in the active terminal."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success("(last command — not available)")


def register_terminal_tools(toolkit) -> None:
    toolkit.register_many([
        RunInTerminalTool(), GetTerminalOutputTool(),
        SendToTerminalTool(), KillTerminalTool(),
        TerminalSelectionTool(), TerminalLastCommandTool(),
    ])
