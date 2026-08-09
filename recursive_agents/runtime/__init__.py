"""
recursive_agents.runtime — the shared runtime of the recursive agent chain.

  toolkit         AgentToolkit: the per-agent REAL tool registry (sync port
                  of the Copilot tool architecture) — the agent-construction
                  tools (agent_plan / agent_generate / agent_create /
                  agent_evaluate / agent_test / agent_improve /
                  agent_deploy / agent_status) are REAL filesystem tools
                  that write the next agent's folders and construct its IPP
                  nodes.
  engine          RecursiveAgentEngine: the agentic loop of every level.
  engine_handlers Ω factories of the engine node (ground / chat /
                  chat_stream).
  templates       the F-file + Ω/Ξ + README + prompt sources (rendered per
                  agent by the toolkit's agent_generate tool).
"""
from recursive_agents.runtime.engine import (  # noqa: F401
    RECURSIVE_TOOL_NAMES, RecursiveAgentEngine,
)
from recursive_agents.runtime.toolkit import (  # noqa: F401
    AgentToolkit, BaseTool, ToolContext, ToolResult,
)

__all__ = ["AgentToolkit", "RecursiveAgentEngine", "RECURSIVE_TOOL_NAMES",
           "BaseTool", "ToolContext", "ToolResult"]
