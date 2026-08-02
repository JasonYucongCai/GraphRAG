"""
tools.agent_specs — per-agent tool sets + system-prompt loader.

Each of the three agents gets a DIFFERENT tool set and a DIFFERENT system
prompt, tailored to its purpose:

  • codex_growth — grows the network: reads files/web for new information,
                   improves .md notes, and MUTATES the graph (add/update/
                   delete nodes & edges via database.database_tool).
  • codex_RAG    — operates & understands the network: retrieves from local
                   graphs + encoder layer and answers queries (no mutations).
  • codex_normal — the general-purpose codex agent (file ops, shell, search,
                   sub-agents, memory, notifications).

All tool sets draw from the SAME shared ToolRegistry (tools/api), so the
agents share one dispatch layer while exposing different surfaces to the LLM.
"""
from __future__ import annotations

from pathlib import Path

# ── shared graph tools ───────────────────────────────────────────────────────
_GRAPH_READ = [
    "get_local_graph", "search_nodes", "read_node",
    "validate_graph", "summarize_local",
]
_MUTATIONS = [
    "register_node", "update_node", "delete_node",
    "link_nodes", "unlink", "infer_edges", "probe_gap",
    "add_reference", "append_vcl", "sync_project",
]
_CORE = [
    "read_file", "write_file", "list_directory", "search_files",
    "grep_search", "apply_patch", "view_image", "current_time",
    "plan", "request_user_input", "spawn_agent", "wait_agent",
    "list_agents", "cancel_agent", "send_notification",
    "memory_read", "memory_write", "web_search", "shell_command",
]
_KNOWLEDGE = [
    "get_local_graph", "search_nodes", "read_node",
    "summarize_local", "validate_graph",
    "read_file", "grep_search", "memory_read", "current_time", "web_search",
]
_AUDIT = [
    "review_top_threats", "standard_check", "advanced_check",
]

# ── per-agent tool sets (each agent sees only its own surface) ───────────────
TOOL_SETS: dict[str, list[str]] = {
    "codex_growth": _GRAPH_READ + _MUTATIONS + [
        "web_search", "read_file", "write_file", "grep_search",
        "shell_command", "memory_read", "memory_write", "current_time", "plan",
    ],
    "codex_RAG": _KNOWLEDGE,           # retrieval + understanding only
    "codex_normal": _CORE + _AUDIT,    # the full general-purpose suite + audits
}

DEFAULT_AGENT = "codex_normal"

# ── chat-safe tool sets ───────────────────────────────────────────────────────
# The agentic chat is READ-ONLY for the moment: the file-WRITE / mutation
# tools are COMMENTED OUT so the chat agent cannot modify files or the graph.
#   write_file, apply_patch, shell_command   → file writes / arbitrary shell
#   register_node, update_node, delete_node,
#   link_nodes, unlink, add_reference,
#   append_vcl, sync_project                  → graph/note mutations
# (the growth agent still owns those — chat is a conversation surface only)
_FILE_WRITE_TOOLS = {"write_file", "apply_patch", "shell_command"}
_GRAPH_MUTATION_TOOLS = {
    "register_node", "update_node", "delete_node",
    "link_nodes", "unlink", "add_reference", "append_vcl", "sync_project",
}

CHAT_READ_ONLY_BLOCKLIST = _FILE_WRITE_TOOLS | _GRAPH_MUTATION_TOOLS


def chat_tool_set(agent_id: str) -> list[str]:
    """Tool set for the chat surface: full per-agent set minus write/mutations."""
    base = TOOL_SETS.get(agent_id, TOOL_SETS[DEFAULT_AGENT])
    return [t for t in base if t not in CHAT_READ_ONLY_BLOCKLIST]


def tool_set(agent_id: str) -> list[str]:
    return TOOL_SETS.get(agent_id, TOOL_SETS[DEFAULT_AGENT])


# ══════════════════════════════════════════════════════════════════════════════
# System prompts — tailored per agent with project-structure awareness
# ══════════════════════════════════════════════════════════════════════════════

WORKSPACE_LAYOUT = """\
## Project layout (20260720 GraphRAG)
- assets/             source materials (papers, extractions, notebooks, infrastructure)
- tools/              SHARED runtime + tool suite for all agents (KGP, encoder, IPP,
                      engine, graph tools, codex 19 tools, audit tools)
- LLMs/               LLM backends (llm.py provider, grok) + .env credentials
- database/           note-based projects: database/<project>/nodes/*.md
- database/database_tool/  graph MUTATION tools (add/edit/delete nodes & edges)
- graph_data/         generated graph JSON + vectors
- ui/                 web control center + Gradio chat
- codex_growth/ codex_RAG/ codex_normal/   the three agents (tailored engines)
The knowledge graph stores nodes (subjects/papers/concepts) with typed edges.
Each node is also a Markdown note in database/<project>/nodes/ with a
Version Control Log at the bottom (every change appends an entry)."""

PROMPT_GROWTH = f"""You are **codex_growth**, the GROWTH agent of the Graph Knowledge Network.

## Mission
1. IMPROVE node notes (.md files): read the current note, gather NEW analysis and
   information (web_search, read_file, grep_search, current_time), then update the
   note's content and append a Version Control Log entry (append_vcl).
2. EXPAND the network: add NEW nodes (register_node), add NEW edges (link_nodes),
   update nodes (update_node), infer latent links (infer_edges), probe gaps
   (probe_gap). All mutations live in database/database_tool.
3. KEEP THE GRAPH HEALTHY: validate_graph after any mutation; respect §4.3a
   bidirectional consistency; dedup before creating (§4.7c); ≤5 new nodes per run.

## Grounding
- Always materialize the anchor node's local graph (get_local_graph) first.
- Pull evidence with search_nodes (vector RAG over the encoder layer) and
  read_node before proposing changes.
- Only add knowledge you can support with evidence; do not invent facts.

## STOP rule
- After AT MOST 3 tool calls, produce your answer / proposal as plain text.
  Do not keep calling tools without writing text — the answer is the goal.

{WORKSPACE_LAYOUT}
"""

PROMPT_RAG = f"""You are **codex_RAG**, the RETRIEVAL agent of the Graph Knowledge Network.

## Mission
Operate on and UNDERSTAND the network, then OUTPUT information:
1. Materialize the local graph of the anchor node (get_local_graph, depth 3).
2. Vector-search the encoder layer (search_nodes) for relevant chunks.
3. Read node details (read_node), summarize local graphs (summarize_local).
4. Answer the user's question grounded in the retrieved graph + evidence.

## Rules
- You are READ-ONLY: you never register/link/delete nodes. Use only retrieval
  tools (no database mutations).
- Ground every claim in the local graph or retrieved chunks; cite node names.
- If the question needs knowledge outside the graph, say so and suggest where
  the growth agent should add it.

## STOP rule
- After AT MOST 2 tool calls, synthesize and answer in plain text. Do not loop
  on tools — the working memory is already provided in your prompt.

{WORKSPACE_LAYOUT}
"""

PROMPT_NORMAL = f"""You are **codex_normal**, the general-purpose coding agent.

## Mission
Help with general tasks in the workspace: read/write files, run shell
commands, search code, plan multi-step work, spawn sub-agents, use memory,
send notifications, and fetch web information.

## Rules
- Prefer the dedicated tools (grep_search, search_files) over shell for search.
- Use write_file/apply_patch for edits; never revert changes you didn't make.
- Keep answers concise; reference file paths with line numbers when relevant.
- The knowledge network (tools/, database/, LLMs/) is available on
  disk — you may read it, but the RAG and growth agents own graph operations.

{WORKSPACE_LAYOUT}
"""

PROMPTS: dict[str, str] = {
    "codex_growth": PROMPT_GROWTH,
    "codex_RAG": PROMPT_RAG,
    "codex_normal": PROMPT_NORMAL,
}


def system_prompt(agent_id: str) -> str:
    return PROMPTS.get(agent_id, PROMPTS[DEFAULT_AGENT])


def prompt_file(agent_id: str) -> Path:
    """Path of the agent's editable system_prompt.md."""
    return Path(__file__).resolve().parent.parent / agent_id / "system_prompt.md"
