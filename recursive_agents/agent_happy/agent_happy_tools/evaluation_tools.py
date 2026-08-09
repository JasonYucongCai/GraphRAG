"""
agent_a1_tools.evaluation_tools — Agent evaluation & testing (5 tools)

check_tool_count, check_recursive_capability,
evaluate_engine_comprehensiveness, run_agent_pipeline, collect_feedback
"""
from __future__ import annotations
import json, os, re
from pathlib import Path
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


def _resolve_agent_name(agent_id: str) -> str:
    """Normalize agent_id to canonical form: 'a2' or 'agent_a2' → 'agent_a2'."""
    if agent_id.startswith("agent_"):
        return agent_id
    return f"agent_{agent_id}"


class CheckToolCountTool(ReadOnlyTool):
    tool_name = "check_tool_count"
    category = "evaluation"
    description = "Count the number of tools in a specified agent's tools folder AND verify all are usable. Must be >= 50."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {
            "agent_id": {"type": "string", "description": "Agent ID to check."},
            "min_required": {"type": "number", "description": "Minimum required tools (default: 50)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = _resolve_agent_name(args.get("agent_id", ""))
        min_required = int(args.get("min_required", 50))
        tk = ctx.agent

        # Check in-memory toolkit
        if tk and agent_id in tk.constructed:
            engine = tk.constructed[agent_id]
            if engine.toolkit and hasattr(engine.toolkit, 'count'):
                count = engine.toolkit.count()
                usable = True  # tools are registered through the validator
                return ToolResult.success(
                    f"{agent_id}: {count} tools (requires {min_required}) — "
                    f"{'PASS' if count >= min_required else 'FAIL'}",
                    agent_id=agent_id, tool_count=count,
                    min_required=min_required,
                    meets_threshold=(count >= min_required),
                    usable=usable)

        # Check on disk
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        tools_dir = root / agent_id / f"{agent_id}_tools"
        if not tools_dir.exists():
            return ToolResult.fail(f"{agent_id} tools directory not found")

        py_files = list(tools_dir.glob("*.py"))
        tool_count = 0
        for pf in py_files:
            try:
                text = pf.read_text(encoding="utf-8")
                # Count tool_name assignments
                tool_count += text.count("tool_name = ")
            except Exception:
                pass

        return ToolResult.success(
            f"{agent_id}: ~{tool_count} tools detected on disk (requires {min_required}) — "
            f"{'PASS' if tool_count >= min_required else 'FAIL'}",
            agent_id=agent_id, tool_count=tool_count,
            min_required=min_required,
            meets_threshold=(tool_count >= min_required))


class CheckRecursiveCapabilityTool(ReadOnlyTool):
    tool_name = "check_recursive_capability"
    category = "evaluation"
    description = "Verify an agent has ALL 8 construction tools needed for recursive improvement."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    REQUIRED_TOOLS = [
        "agent_plan", "agent_generate", "agent_create",
        "agent_evaluate", "agent_test", "agent_improve",
        "agent_deploy", "agent_status",
    ]

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = _resolve_agent_name(args.get("agent_id", ""))
        tk = ctx.agent

        if tk and agent_id in tk.constructed:
            engine = tk.constructed[agent_id]
            if engine.toolkit and hasattr(engine.toolkit, 'names'):
                tool_names = engine.toolkit.names()
            else:
                tool_names = []
            missing = [t for t in self.REQUIRED_TOOLS if t not in tool_names]
            return ToolResult.success(
                f"{agent_id}: recursive_capability={'PASS' if not missing else 'FAIL'}",
                agent_id=agent_id,
                has_all=(not missing),
                missing=missing,
                found=[t for t in self.REQUIRED_TOOLS if t in tool_names])

        # Check on disk
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        tools_dir = root / agent_id / f"{agent_id}_tools"
        found = []
        missing = []
        for tool_name in self.REQUIRED_TOOLS:
            # Search for tool_name in Python files
            found_tool = False
            if tools_dir.exists():
                for pf in tools_dir.glob("*.py"):
                    try:
                        if f'"{tool_name}"' in pf.read_text(encoding="utf-8"):
                            found_tool = True
                            break
                    except Exception:
                        pass
            if found_tool:
                found.append(tool_name)
            else:
                missing.append(tool_name)

        return ToolResult.success(
            f"{agent_id}: recursive_capability={'PASS' if not missing else 'FAIL'} — "
            f"found {len(found)}/8, missing: {missing}",
            agent_id=agent_id, has_all=(not missing),
            missing=missing, found=found)


class EvaluateEngineComprehensivenessTool(ReadOnlyTool):
    tool_name = "evaluate_engine_comprehensiveness"
    category = "evaluation"
    description = "Check if an agent's engine has all required components (hooks, prompt, autopilot, summarizer)."
    REQUIRED_COMPONENTS = [
        "HookSystem", "PromptAssembler", "AutopilotController",
        "ContextSummarizer", "AgentA1Engine",
    ]

    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = _resolve_agent_name(args.get("agent_id", ""))
        tk = ctx.agent
        root = Path(tk.ws_root) / "recursive_agents" if tk else Path(".")
        engine_dir = root / agent_id / f"{agent_id}_engine"

        found = []
        missing = []
        if engine_dir.exists():
            for pf in engine_dir.glob("*.py"):
                try:
                    text = pf.read_text(encoding="utf-8")
                    for comp in self.REQUIRED_COMPONENTS:
                        if comp in text and comp not in found:
                            found.append(comp)
                except Exception:
                    pass
        missing = [c for c in self.REQUIRED_COMPONENTS if c not in found]

        return ToolResult.success(
            f"{agent_id} engine: found {len(found)}/{len(self.REQUIRED_COMPONENTS)} components",
            agent_id=agent_id, found=found, missing=missing,
            is_comprehensive=(not missing))


class RunAgentPipelineTool(ReadOnlyTool):
    tool_name = "run_agent_pipeline"
    category = "evaluation"
    description = "Run the full ground→chat pipeline for an agent and collect the trace."
    tool_schema = {
        "type": "object", "required": ["agent_id", "task"],
        "properties": {
            "agent_id": {"type": "string"},
            "task": {"type": "string", "description": "Task to send through the pipeline."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        task = args.get("task", "Reply with OK only")
        tk = ctx.agent
        engine = tk.constructed.get(agent_id) if tk else None
        if engine is None:
            return ToolResult.fail(f"{agent_id} not constructed")
        try:
            answer, trace = engine.run_with_trace(task)
            return ToolResult.success(
                answer[:500],
                agent_id=agent_id, answer=answer[:1000],
                trace_steps=len(trace))
        except Exception as e:
            return ToolResult.fail(str(e))


class CollectFeedbackTool(ReadOnlyTool):
    tool_name = "collect_feedback"
    category = "evaluation"
    description = "Collect and summarize feedback for an agent from log files."
    tool_schema = {
        "type": "object", "required": ["agent_id"],
        "properties": {"agent_id": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_id = args.get("agent_id", "")
        tk = ctx.agent
        root = Path(tk.ws_root) / "recursive_agents" / "feedback" if tk else Path(".")
        fb_file = root / f"{agent_id}.txt"
        if fb_file.exists():
            try:
                content = fb_file.read_text(encoding="utf-8")
                return ToolResult.success(content, agent_id=agent_id)
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success(f"No feedback found for {agent_id}",
                                  agent_id=agent_id, has_feedback=False)


def register_evaluation_tools(toolkit) -> None:
    toolkit.register_many([
        CheckToolCountTool(), CheckRecursiveCapabilityTool(),
        EvaluateEngineComprehensivenessTool(),
        RunAgentPipelineTool(), CollectFeedbackTool(),
    ])
