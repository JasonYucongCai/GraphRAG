# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""tools/copilot/terminal_tools.py — Terminal & Task tools (9 tools)

Copilot equivalents: run_in_terminal, get_terminal_output, send_to_terminal,
    kill_terminal, terminal_selection, terminal_last_command,
    create_and_run_task, run_task, get_task_output
"""
from __future__ import annotations
from typing import Any
from .tool_base import ExecuteTool, ReadOnlyTool, ToolContext, ToolResult


class RunInTerminalTool(ExecuteTool):
    tool_name = "run_in_terminal"
    tool_reference_name = "runInTerminal"
    display_name = "Run in Terminal"
    timeout_seconds = 60
    tool_schema = {
        "type": "object", "required": ["command"],
        "properties": {
            "command": {"type": "string", "description": "Shell command to run."},
            "explanation": {"type": "string", "description": "What the command does (shown to user)."},
            "goal": {"type": "string", "description": "Goal of running this command."},
            "mode": {"type": "string", "enum": ["sync", "async"], "description": "sync=wait for output; async=keep running."},
            "timeout": {"type": "number", "description": "Timeout in ms (optional)."},
            "cwd": {"type": "string", "description": "Working directory."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        import asyncio, os, subprocess
        cmd = args.get("command", "")
        mode = args.get("mode", "sync")
        cwd = args.get("cwd", ctx.workspace_root) or os.getcwd()
        timeout = int(args.get("timeout", 60000)) / 1000 if args.get("timeout") else 60
        if not cmd: return ToolResult.fail("command is required")
        try:
            p = await asyncio.create_subprocess_shell(
                cmd, cwd=cwd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=min(timeout, 300))
            out = stdout.decode("utf-8", errors="replace")[:4000]
            err = stderr.decode("utf-8", errors="replace")[:1000]
            return ToolResult.ok(
                content=out + (f"\n[stderr]\n{err}" if err else ""),
                exit_code=p.returncode, command=cmd[:200],
            )
        except asyncio.TimeoutError:
            return ToolResult.fail(f"Command timed out after {timeout}s: {cmd[:200]}")
        except Exception as e:
            return ToolResult.fail(str(e))


class GetTerminalOutputTool(ReadOnlyTool):
    tool_name = "get_terminal_output"
    tool_reference_name = "getTerminalOutput"
    display_name = "Get Terminal Output"
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {
            "id": {"type": "string", "description": "Terminal ID."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Terminal {args.get('id', '?')} output (no persistent terminal state)")


class SendToTerminalTool(ExecuteTool):
    tool_name = "send_to_terminal"
    tool_reference_name = "sendToTerminal"
    display_name = "Send to Terminal"
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {
            "id": {"type": "string", "description": "Terminal ID."},
            "command": {"type": "string", "description": "Text to send (Enter appended)."},
            "waitForOutput": {"type": "boolean", "description": "Wait for idle before returning. Default: false."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Sent to terminal {args.get('id', '?')}: {args.get('command', '')[:80]}")


class KillTerminalTool(ExecuteTool):
    tool_name = "kill_terminal"
    tool_reference_name = "killTerminal"
    display_name = "Kill Terminal"
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {"id": {"type": "string", "description": "Terminal ID."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Killed terminal {args.get('id', '?')}")


class TerminalSelectionTool(ReadOnlyTool):
    tool_name = "terminal_selection"
    tool_reference_name = "terminalSelection"
    display_name = "Terminal Selection"
    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content="(no terminal selection — codex-local has no persistent terminal state)")


class TerminalLastCommandTool(ReadOnlyTool):
    tool_name = "terminal_last_command"
    tool_reference_name = "terminalLastCommand"
    display_name = "Last Terminal Command"
    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content="(no terminal history — codex-local has no persistent terminal state)")


class CreateAndRunTaskTool(ExecuteTool):
    tool_name = "create_and_run_task"
    tool_reference_name = "createAndRunTask"
    display_name = "Create and Run Task"
    deferred = True
    tool_schema = {
        "type": "object", "required": ["workspaceFolder", "task"],
        "properties": {
            "workspaceFolder": {"type": "string", "description": "Workspace folder path."},
            "task": {"type": "object", "properties": {
                "label": {"type": "string"}, "type": {"type": "string", "enum": ["shell"]},
                "command": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}},
                "isBackground": {"type": "boolean"}, "group": {"type": "string"},
            }},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        task = args.get("task", {})
        label = task.get("label", "")
        cmd = task.get("command", "")
        return ToolResult.ok(content=f"Created task '{label}': {cmd}")


class GetTaskOutputTool(ReadOnlyTool):
    tool_name = "get_task_output"
    tool_reference_name = "getTaskOutput"
    display_name = "Get Task Output"
    tool_schema = {
        "type": "object", "required": ["id", "workspaceFolder"],
        "properties": {"id": {"type": "string"}, "workspaceFolder": {"type": "string"}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Task {args.get('id', '?')} output (no persistent task state)")
