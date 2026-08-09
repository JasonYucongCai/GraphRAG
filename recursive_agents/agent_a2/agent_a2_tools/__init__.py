"""
agent_a2_tools — the comprehensive tool suite of agent_a2.

74 tools in 15 categories, NOT weaker than assets/copilot_agent_tools.
Includes the agent-construction suite with which agent_a2 creates agent_a2.

Categories (74 tools total):
  agent_construction (8)  — plan, generate, create, evaluate, test, improve, deploy, status
  file (6)               — read, write, replace, multi-replace, create_dir, list_dir
  search (4)             — grep, file_search, search_nodes, find_references
  terminal (6)           — run_in_terminal, get_output, send, kill, selection, last_cmd
  memory (5)             — read, write, list, delete, search
  graph (8)              — get_local_graph, read_node, validate, summarize, projects, etc.
  ipp (5)                — construct, verify, audit, status_report, check_invariants
  llm (3)                — chat, check, provider_info
  evaluation (5)         — check_tool_count, check_recursive_capability, engine_comprehensiveness, etc.
  documentation (4)      — write_readme, write_system_prompt, generate_docs, read_docs
  log (5)                — write_log, read_log, list_logs, write_feedback, read_feedback
  web (3)                — web_search, fetch_webpage, download_arxiv
  system (5)             — current_time, get_env, check_python, list_packages, system_info
  powershell (3)         — start_agent, stop_agent, check_agent_status
  code (4)               — validate, compile_check, run_snippet, generate_python_file

Built strictly per IPP v0.2.8. Every tool has the four-phase lifecycle:
resolve_input → validate → prepare → invoke.
"""
from .tool_base import BaseTool, ReadOnlyTool, EditTool, ExecuteTool, WebTool, MemoryTool, ToolContext, ToolResult
from .tool_registry import AgentA1Toolkit
from .agent_construction_tools import (
    AgentPlanTool, AgentGenerateTool, AgentCreateTool,
    AgentEvaluateTool, AgentTestTool, AgentImproveTool,
    AgentDeployTool, AgentStatusTool,
)

# Ensure all tool modules are importable
__all__ = [
    "BaseTool", "ReadOnlyTool", "EditTool", "ExecuteTool", "WebTool", "MemoryTool",
    "ToolContext", "ToolResult",
    "AgentA1Toolkit",
    "AgentPlanTool", "AgentGenerateTool", "AgentCreateTool",
    "AgentEvaluateTool", "AgentTestTool", "AgentImproveTool",
    "AgentDeployTool", "AgentStatusTool",
]
