# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/shell_tools.py — Shell Command, Terminal, and Task Tools

Copilot equivalents: run_in_terminal, get_terminal_output, send_to_terminal, etc.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Any

from .tool_base import ExecuteTool, ReadOnlyTool, ToolContext, ToolResult

# Block destructive patterns by default
DESTRUCTIVE_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"dd\s+if=",
    r"mkfs\.",
    r">\s*/dev/sd",
    r"format\s+[A-Z]:",
    r"del\s+/[fsq].*\\Windows",
    r"rmdir\s+/[sq].*\\Windows",
]


class ShellCommandTool(ExecuteTool):
    tool_name = "shell_command"
    tool_reference_name = "runInTerminal"
    display_name = "Shell Command"
    user_description = "Execute a shell command and return the output"
    tags = ["execute"]
    timeout_seconds = 60

    tool_schema = {
        "type": "object",
        "required": ["command"],
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory. Defaults to workspace root.",
            },
            "timeout_seconds": {
                "type": "number",
                "description": f"Timeout in seconds. Default: {timeout_seconds}, max: 300.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        command = args.get("command", "")
        cwd = args.get("cwd") or context.workspace_root or context.working_directory or os.getcwd()
        timeout = min(int(args.get("timeout_seconds", self.timeout_seconds)), 300)

        if not command:
            return ToolResult.fail("command is required")

        # Check for destructive patterns
        import re as _re
        for pat in DESTRUCTIVE_PATTERNS:
            if _re.search(pat, command, _re.IGNORECASE):
                return ToolResult.fail(
                    f"Blocked potentially destructive command: {command[:80]}",
                    error_type="blocked_destructive",
                )

        cwd = os.path.abspath(os.path.expanduser(cwd))
        if not os.path.isdir(cwd):
            cwd = os.getcwd()

        try:
            # Use conda env prefix if configured
            prefix = ""
            try:
                from config import Config
                prefix = Config.get_conda_activate_prefix()
            except ImportError:
                pass

            full_cmd = f"{prefix}{command}" if prefix else command

            process = await asyncio.create_subprocess_shell(
                full_cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult.fail(
                    f"Command timed out after {timeout}s.\n"
                    f"Command: {command[:200]}",
                    error_type="timeout",
                )

            output = stdout.decode("utf-8", errors="replace")
            err_out = stderr.decode("utf-8", errors="replace")

            result_lines = []
            if output:
                result_lines.append(output.rstrip())
            if err_out:
                result_lines.append(f"\n[stderr]\n{err_out.rstrip()}")

            return ToolResult.ok(
                content="\n".join(result_lines) if result_lines else f"[Command completed with exit code {process.returncode}]",
                exit_code=process.returncode,
                command=command[:200],
                cwd=cwd,
            )

        except FileNotFoundError:
            return ToolResult.fail(f"Command not found: {command.split()[0] if command else ''}")
        except Exception as e:
            return ToolResult.fail(f"Error executing command: {e}")


class PlanTool(ReadOnlyTool):
    """Create structured task plans with steps, statuses, and dependencies.

    This is a CREATE-ONLY tool — use manage_todo_list for tracking progress.
    """
    tool_name = "plan"
    display_name = "Create Plan"
    tags = ["core"]

    tool_schema = {
        "type": "object",
        "required": ["title", "steps"],
        "properties": {
            "title": {"type": "string", "description": "Plan title"},
            "steps": {
                "type": "array",
                "description": "List of plan steps",
                "items": {
                    "type": "object",
                    "required": ["id", "description"],
                    "properties": {
                        "id": {"type": "string", "description": "Short step ID (1, 2, 3, ...)"},
                        "description": {"type": "string"},
                        "depends_on": {
                            "type": "array", "items": {"type": "string"},
                            "description": "IDs of steps that must complete first",
                        },
                    },
                },
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        title = args.get("title", "Plan")
        steps = args.get("steps", [])

        output = [f"## Plan: {title}", ""]
        for s in steps:
            sid = s.get("id", "?")
            desc = s.get("description", "")
            deps = s.get("depends_on", [])
            dep_str = f" (depends: {', '.join(deps)})" if deps else ""
            output.append(f"- [ ] **{sid}**: {desc}{dep_str}")

        return ToolResult.ok(
            content="\n".join(output),
            plan_title=title, step_count=len(steps),
        )


class ManageTodoListTool(ReadOnlyTool):
    """Manage a structured todo list for tracking progress across turns."""
    tool_name = "manage_todo_list"
    tool_reference_name = "manageTodoList"
    display_name = "Manage Todo List"
    tags = ["core"]

    tool_schema = {
        "type": "object",
        "required": ["todo_list"],
        "properties": {
            "todo_list": {
                "type": "array",
                "description": "Complete array of all todo items.",
                "items": {
                    "type": "object",
                    "required": ["id", "title", "status"],
                    "properties": {
                        "id": {"type": "number", "description": "Unique sequential ID starting from 1"},
                        "title": {"type": "string", "description": "3-7 word action label"},
                        "status": {
                            "type": "string",
                            "enum": ["not-started", "in-progress", "completed"],
                        },
                    },
                },
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        todos = args.get("todo_list", args.get("todoList", []))
        if not todos:
            return ToolResult.ok(content="No todo items.")

        status_icons = {"not-started": "⬜", "in-progress": "🔄", "completed": "✅"}
        lines = ["## Progress"]
        for t in todos:
            icon = status_icons.get(t.get("status", "not-started"), "⬜")
            lines.append(f"- {icon} {t.get('id', '?')}. {t.get('title', '')}")

        completed = sum(1 for t in todos if t.get("status") == "completed")
        total = len(todos)
        lines.append(f"\nProgress: {completed}/{total} ({int(completed/total*100) if total else 0}%)")
        return ToolResult.ok(content="\n".join(lines), completed=completed, total=total)


class TaskCompleteTool(ReadOnlyTool):
    """Signal that the task is complete — used by autopilot to detect completion."""
    tool_name = "task_complete"
    tool_reference_name = "taskComplete"
    display_name = "Task Complete"
    tags = ["core"]

    tool_schema = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of what was accomplished.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        summary = args.get("summary", "Task completed.")
        return ToolResult.ok(content=f"[TASK_COMPLETE] {summary}", task_complete=True)
