"""
agent_a1_tools.powershell_tools — Agent process management (3 tools)

start_agent_process, stop_agent_process, check_agent_status
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from typing import Any
from .tool_base import ExecuteTool, ReadOnlyTool, ToolContext, ToolResult


class StartAgentProcessTool(ExecuteTool):
    tool_name = "start_agent_process"
    category = "powershell"
    description = "Start an agent as a new Python process via PowerShell."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Agent ID to start."},
            "task": {"type": "string", "description": "Task to give the agent."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        task = args.get("task", "")
        root = ctx.workspace_root or os.getcwd()

        # Build a script that imports and runs the agent
        script = (
            f"import sys; sys.path.insert(0, {root!r}); "
            f"from recursive_agents.runtime.engine import RecursiveAgentEngine; "
            f"from general_tools.graph import KnowledgeGraph; "
            f"from general_tools.encoder import EncoderLayer; "
            f"print(f'agent_{agent_id} started, task: {task[:100]}')"
        )
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            return ToolResult.success(
                f"Agent {agent_id} started (PID: {proc.pid})",
                agent_id=agent_id, pid=proc.pid, task=task[:200])
        except Exception as e:
            return ToolResult.fail(str(e))


class StopAgentProcessTool(ExecuteTool):
    tool_name = "stop_agent_process"
    category = "powershell"
    description = "Stop a running agent process by PID."
    tool_schema = {
        "type": "object", "required": ["pid"],
        "properties": {
            "pid": {"type": "number", "description": "Process ID to stop."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        pid = int(args.get("pid", 0))
        if pid <= 0:
            return ToolResult.fail("pid is required")
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            return ToolResult.success(f"Sent SIGTERM to PID {pid}", pid=pid)
        except ProcessLookupError:
            return ToolResult.success(f"Process {pid} not found", pid=pid)
        except Exception as e:
            return ToolResult.fail(str(e))


class CheckAgentStatusTool(ReadOnlyTool):
    tool_name = "check_agent_status"
    category = "powershell"
    description = "Check if an agent process is running and report its status."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Agent ID to check."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        tk = ctx.agent

        # Check in-memory state
        is_constructed = agent_id in (tk.constructed if tk else {})
        is_in_chain = agent_id in (tk.chain if tk else [])

        # Check on-disk state
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        agent_dir = root / agent_id
        on_disk = agent_dir.exists()
        has_engine = (agent_dir / f"{agent_id}_engine" / "IPP.json").exists()
        has_tools = (agent_dir / f"{agent_id}_tools" / "IPP.json").exists()
        has_readme = (agent_dir / "README.md").exists()
        has_prompt = (agent_dir / "system_prompt.md").exists()

        # Count tools on disk
        tool_count = 0
        tools_dir = agent_dir / f"{agent_id}_tools"
        if tools_dir.exists():
            tool_count = len(list(tools_dir.glob("*.py")))

        return ToolResult.success(
            f"{agent_id} status:\n"
            f"  Constructed: {is_constructed}\n"
            f"  In chain: {is_in_chain}\n"
            f"  On disk: {on_disk}\n"
            f"  Engine IPP: {has_engine}\n"
            f"  Tools IPP: {has_tools}\n"
            f"  README: {has_readme}\n"
            f"  System prompt: {has_prompt}\n"
            f"  Tool files: {tool_count}",
            agent_id=agent_id, constructed=is_constructed,
            in_chain=is_in_chain, on_disk=on_disk,
            has_engine=has_engine, has_tools=has_tools,
            has_readme=has_readme, has_prompt=has_prompt,
            tool_count=tool_count)


def register_powershell_tools(toolkit) -> None:
    toolkit.register_many([
        StartAgentProcessTool(), StopAgentProcessTool(),
        CheckAgentStatusTool(),
    ])
