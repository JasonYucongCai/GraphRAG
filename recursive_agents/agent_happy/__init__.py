"""
agent_happy — the FIRST recursive agent of the self-adaptive chain, level 1.

Constructed strictly per IPP v0.2.8. This is the FIRST COMPILATION —
the agent whose tools CREATE agent_a2, which then creates agent_a3.

Architecture:
  agent_happy_engine/  — Enhanced engine (hooks, prompt assembler, autopilot, summarizer)
  agent_happy_tools/   — 74 tools in 15 categories including the agent-construction suite
  system_prompt.md  — The system prompt that drives the agent
  README.md         — This agent's documentation

The engine is the LOOP; the tools are the HANDS. Agent a1 creates a2
through its OWN tools — not through a bootstrap script.
"""
from .agent_happy_engine import (
    AgentA1Engine, HookSystem, PromptAssembler,
    AutopilotController, ContextSummarizer,
)
from .agent_happy_tools import (
    AgentA1Toolkit, BaseTool, ToolContext, ToolResult,
)
