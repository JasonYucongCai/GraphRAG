# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/sub_agent.py — Sub-Agent Tools (Search, Execution, Exploration)

Copilot equivalents: searchSubagentTool.ts, executionSubagentTool.ts

These are "tools that call tools" — they spawn nested agent loops that
can use a subset of tools to accomplish sub-tasks and return results.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from .tool_base import BaseTool, ToolContext, ToolResult, ToolCallEvent


class SearchSubagentTool(BaseTool):
    """Spawn a sub-agent optimized for codebase exploration.

    The sub-agent can use read_file, list_directory, search_files, and
    grep_search to find answers and return them.
    """
    tool_name = "search_subagent"
    tool_reference_name = "searchSubagent"
    display_name = "Search Sub-Agent"
    deferred = True
    tags = ["sub-agent", "search"]

    tool_schema = {
        "type": "object",
        "required": ["query", "description"],
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what to search for.",
            },
            "description": {
                "type": "string",
                "description": "User-visible description shown while the sub-agent runs.",
            },
            "thoroughness": {
                "type": "string",
                "enum": ["quick", "medium", "thorough"],
                "description": "Search depth. Default: medium.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        query = args.get("query", "")
        description = args.get("description", query[:60])
        thoroughness = args.get("thoroughness", "medium")

        # Tool limits by thoroughness
        limits = {"quick": 5, "medium": 10, "thorough": 20}
        max_rounds = limits.get(thoroughness, 10)

        agent_id = str(uuid.uuid4())[:8]

        # Sub-agent gets a restricted tool set: read-only search tools
        sub_agent_prompt = f"""You are a fast search sub-agent for codebase exploration.
Your task: {query}

Available tools: read_file, list_directory, search_files, grep_search, view_image
You have {max_rounds} tool call rounds. Be concise and return only factual findings.
Do NOT modify any files. Return your findings as clear bullet points or structured text.

IMPORTANT: When you've found the answer, respond with it directly (no more tool calls)."""

        try:
            # Create sub-agent with restricted tools
            sub_context = ToolContext(
                workspace_root=context.workspace_root,
                session_id=f"{context.session_id}_sub_{agent_id}",
                request_id=context.request_id,
                agent_name=f"search_subagent_{agent_id}",
                working_directory=context.working_directory,
                allowed_paths=context.allowed_paths,
                cancelled=context.cancelled,
            )

            # Get a sub-engine (lazy import to avoid circular)
            from agents.codex.engine import CodexEngine
            sub_agent = CodexEngine(
                model=None,  # inherits from parent
                tools=None,  # will be filtered
            )
            sub_agent.messages = [{"role": "system", "content": sub_agent_prompt}]
            sub_agent.MAX_TOOL_ROUNDS = max_rounds

            # Only enable read-only tools
            sub_agent._tool_filter = {"read_file", "list_directory", "search_files", "grep_search", "view_image"}

            result_text = await asyncio.to_thread(sub_agent.chat, query, verbose=False)

            return ToolResult.ok(
                content=result_text or "Search sub-agent returned no results.",
                sub_agent_id=agent_id,
                rounds_used=getattr(sub_agent, "rounds_used", 0),
            )

        except Exception as e:
            return ToolResult.fail(
                f"The search sub-agent failed: {e}",
                error_type="subagent_error",
                sub_agent_id=agent_id,
            )


class ExecutionSubagentTool(BaseTool):
    """Spawn a sub-agent that can run shell commands and return results.

    Used for tasks like running tests, installing dependencies, building,
    or any command-line operation that needs to be isolated.
    """
    tool_name = "execution_subagent"
    tool_reference_name = "executionSubagent"
    display_name = "Execution Sub-Agent"
    deferred = True
    tags = ["sub-agent", "execute"]

    tool_schema = {
        "type": "object",
        "required": ["query", "description"],
        "properties": {
            "query": {
                "type": "string",
                "description": "What to execute and what to look for in the output.",
            },
            "description": {
                "type": "string",
                "description": "User-visible description shown while the sub-agent runs.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        query = args.get("query", "")
        description = args.get("description", query[:60])
        agent_id = str(uuid.uuid4())[:8]
        max_rounds = 10

        sub_agent_prompt = f"""You are an execution sub-agent. Your task: {query}

You can run shell commands to:
- Run tests and report results
- Install packages and dependencies
- Build projects
- Run scripts and report output

Available tools: shell_command, read_file, list_directory, search_files, grep_search
You have {max_rounds} tool call rounds. Return results concisely.
When done, respond with a summary of what happened and the key output."""

        try:
            from agents.codex.engine import CodexEngine
            sub_agent = CodexEngine(model=None, tools=None)
            sub_agent.messages = [{"role": "system", "content": sub_agent_prompt}]
            sub_agent.MAX_TOOL_ROUNDS = max_rounds
            sub_agent._tool_filter = {"shell_command", "read_file", "list_directory", "search_files", "grep_search"}

            result_text = await asyncio.to_thread(sub_agent.chat, query, verbose=False)

            return ToolResult.ok(
                content=result_text or "Execution sub-agent returned no output.",
                sub_agent_id=agent_id,
            )
        except Exception as e:
            return ToolResult.fail(
                f"The execution sub-agent failed: {e}",
                error_type="subagent_error",
            )


class SpawnAgentTool(BaseTool):
    """Spawn a fully-independent background sub-agent for long-running tasks.

    Unlike SearchSubagentTool (which waits for results), this returns
    immediately with an agent_id that can be checked via wait_agent.
    """
    tool_name = "spawn_agent"
    tool_reference_name = "spawnAgent"
    display_name = "Spawn Background Agent"
    deferred = True
    tags = ["sub-agent"]

    tool_schema = {
        "type": "object",
        "required": ["name", "task"],
        "properties": {
            "name": {"type": "string", "description": "Human-readable name for this agent."},
            "task": {"type": "string", "description": "The complete task description."},
            "context": {"type": "string", "description": "Additional context for the agent."},
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        name = args.get("name", "sub_agent")
        task = args.get("task", "")
        extra_context = args.get("context", "")
        agent_id = str(uuid.uuid4())[:8]

        prompt = f"""You are a background sub-agent named "{name}".
Task: {task}
{f'Additional context: {extra_context}' if extra_context else ''}
When you complete this task, respond with a clear summary starting with [TASK_COMPLETE]."""

        import threading as _threading

        result_container: dict[str, Any] = {"done": False, "text": "", "error": None}

        def _run():
            try:
                from agents.codex.engine import CodexEngine
                sub = CodexEngine(model=None, tools=None)
                sub.messages = [{"role": "system", "content": prompt}]
                sub.MAX_TOOL_ROUNDS = 15
                result_container["text"] = sub.chat(task, verbose=False)
            except Exception as e:
                result_container["error"] = str(e)
            finally:
                result_container["done"] = True

        thread = _threading.Thread(target=_run, daemon=True)
        thread.start()

        # Store for later retrieval
        if not hasattr(context, "_sub_agents"):
            context.metadata["_sub_agents"] = {}
        context.metadata["_sub_agents"][agent_id] = {
            "name": name, "task": task, "thread": thread,
            "result": result_container, "started_at": __import__("time").time(),
        }

        return ToolResult.ok(
            content=f"Launched background agent '{name}' (ID: {agent_id})",
            agent_id=agent_id, agent_name=name,
        )


class WaitAgentTool(BaseTool):
    """Wait for a background sub-agent to complete."""
    tool_name = "wait_agent"
    tool_reference_name = "waitAgent"
    display_name = "Wait for Agent"
    deferred = True
    tags = ["sub-agent"]

    tool_schema = {
        "type": "object",
        "required": ["agent_id"],
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent ID returned by spawn_agent.",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Max wait time. Default: 120, range: 1-600.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        timeout = min(max(int(args.get("timeout_seconds", 120)), 1), 600)

        sub_agents = context.metadata.get("_sub_agents", {})
        info = sub_agents.get(agent_id)
        if not info:
            return ToolResult.fail(f"No background agent with ID {agent_id!r}. Use list_agents to see active agents.")

        result_container = info["result"]
        elapsed = 0
        while not result_container["done"] and elapsed < timeout:
            await asyncio.sleep(1)
            elapsed += 1

        if not result_container["done"]:
            return ToolResult.fail(f"Agent {agent_id!r} did not complete within {timeout}s.")

        if result_container["error"]:
            return ToolResult.fail(f"Agent {agent_id!r} failed: {result_container['error']}")

        return ToolResult.ok(
            content=result_container["text"] or f"Agent {agent_id!r} completed.",
            agent_id=agent_id,
        )


class ListAgentsTool(BaseTool):
    """List all background sub-agents and their statuses."""
    tool_name = "list_agents"
    tool_reference_name = "listAgents"
    display_name = "List Agents"
    deferred = True
    tags = ["sub-agent"]

    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        sub_agents = context.metadata.get("_sub_agents", {})
        if not sub_agents:
            return ToolResult.ok(content="No background agents running.")

        lines = ["## Background Agents", ""]
        for aid, info in sub_agents.items():
            done = info["result"]["done"]
            status = "✅ Done" if done else "🔄 Running"
            elapsed = __import__("time").time() - info["started_at"]
            lines.append(f"- `{aid}` — {info['name']} ({status}, {elapsed:.0f}s)")
        return ToolResult.ok(content="\n".join(lines), count=len(sub_agents))


class CancelAgentTool(BaseTool):
    """Cancel a running background sub-agent."""
    tool_name = "cancel_agent"
    tool_reference_name = "cancelAgent"
    display_name = "Cancel Agent"
    deferred = True
    tags = ["sub-agent"]

    tool_schema = {
        "type": "object",
        "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        sub_agents = context.metadata.get("_sub_agents", {})
        info = sub_agents.get(agent_id)
        if not info:
            return ToolResult.fail(f"No agent with ID {agent_id!r}.")
        if info["result"]["done"]:
            return ToolResult.ok(content=f"Agent {agent_id!r} already completed.")
        # Mark cancelled
        info["result"]["done"] = True
        info["result"]["error"] = "Cancelled by user"
        return ToolResult.ok(content=f"Cancelled agent {agent_id!r}.")
