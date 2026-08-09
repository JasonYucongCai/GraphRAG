"""
recursive_agents — the self-adaptive recursive agent chain (Section A).

The bootstrap-compiler analogy (Rust / C / C++): there is no
self-improving agent yet, so the first recursive agent — agent_a1 — is
built FOR REAL here (engine + its OWN toolkit), strictly per IPP v0.2.8
(the first structure we know works), and agent_a1 then uses ITS OWN
TOOLS (the agent-construction suite in its tools node) to:

  1. THINK  — `agent_plan`
  2. GENERATE — `agent_generate` (writes the next agent's folders)
  3. CREATE — `agent_create` (Γ constructs its IPP nodes, 17 invariants)
  4. EVALUATE + TEST — `agent_evaluate` / `agent_test` (feedback)
  5. IMPROVE — `agent_improve` (patch until it passes)
  6. DEPLOY — `agent_deploy` (register in the chain)

and agent_a2 has the SAME toolkit: it creates agent_a3.

Layout (each agent's engine and tools live in separate folders, each
with its own F-file, Ω/Ξ modules and README):

  recursive_agents/
    runtime/                ← the shared machinery (toolkit, engine, templates)
    agent_a1/
      README.md  system_prompt.md
      agent_a1_engine/      ← IPP.json + IPP_object.py + IPP_executor.py + README.md
      agent_a1_tools/       ← IPP.json + IPP_object.py + IPP_executor.py + README.md
    agent_a2/  (created BY a1 via its tools)   agent_a3/  (created BY a2)  …

Public API:

    from recursive_agents.runtime.toolkit import AgentToolkit

    toolkit = AgentToolkit(agent_id="agent_a1")
    toolkit.generate("a2", 2)          # a1's REAL tool writes a2's folders
    toolkit.construct("a2", 2)         # Γ constructs a2's IPP nodes
"""
from recursive_agents.runtime import (  # noqa: F401
    RECURSIVE_TOOL_NAMES, AgentToolkit, BaseTool, RecursiveAgentEngine,
    ToolContext, ToolResult,
)

__all__ = ["AgentToolkit", "RecursiveAgentEngine", "RECURSIVE_TOOL_NAMES",
           "BaseTool", "ToolContext", "ToolResult"]
