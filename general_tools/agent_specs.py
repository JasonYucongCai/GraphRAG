"""
tools.agent_specs — per-agent tool sets + system-prompt loader.

Each of the three agents gets a DIFFERENT tool set and a DIFFERENT system
prompt, tailored to its purpose:

  • codex_growth — grows the network: reads files/web for new information,
                   improves .md notes, and MUTATES the graph (add/update/
                   delete nodes & edges via the database node).
  • codex_RAG    — operates & understands the network: retrieves from local
                   graphs + encoder layer and answers queries (no mutations).
  • codex_normal — the general-purpose codex agent (file ops, shell, search,
                   sub-agents, memory, notifications).

All tool sets draw from the SAME tools IPP node (tools/IPP.json via Γ —
the F-file catalogs), so the
agents share one dispatch layer while exposing different surfaces to the LLM.
"""
from __future__ import annotations

from pathlib import Path

# ── shared graph tools ───────────────────────────────────────────────────────
_GRAPH_READ = [
    "get_local_graph", "search_nodes", "read_node",
    "validate_graph", "summarize_local",
    "list_projects", "project_info", "list_supplements", "get_categories",
]
_MUTATIONS = [
    "register_node", "update_node", "delete_node",
    "link_nodes", "unlink", "infer_edges", "probe_gap",
    "add_reference", "append_vcl", "sync_project",
    "create_project", "open_project", "save_graph", "export_interactive",
    "create_supplement", "open_supplement", "close_supplement",
    "sync_supplement", "save_supplement_graph", "add_supplement_asset",
    "update_categories",
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
_SOCIAL = [   # the IPP_Social layer — agents discover it by default
    "social_post", "social_board", "social_agents", "social_goals",
    "social_create_goal", "social_create_task", "social_update_task",
    "social_get_task", "social_inbox",
]

# ── per-agent tool sets (each agent sees only its own surface) ───────────────
TOOL_SETS: dict[str, list[str]] = {
    "codex_growth": _GRAPH_READ + _MUTATIONS + [
        "web_search", "read_file", "write_file", "grep_search",
        "shell_command", "memory_read", "memory_write", "current_time", "plan",
    ],
    "codex_RAG": _KNOWLEDGE,           # retrieval + understanding only
    "codex_normal": _CORE + _AUDIT + _SOCIAL,   # general suite + audits + social
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
    "create_project", "open_project", "save_graph", "export_interactive",
    "create_supplement", "open_supplement", "close_supplement",
    "sync_supplement", "save_supplement_graph", "add_supplement_asset",
    "update_categories",
}

CHAT_READ_ONLY_BLOCKLIST = _FILE_WRITE_TOOLS | _GRAPH_MUTATION_TOOLS


def chat_tool_set(agent_id: str) -> list[str]:
    """Tool set for the chat surface: full per-agent set minus write/mutations."""
    base = TOOL_SETS.get(agent_id, TOOL_SETS[DEFAULT_AGENT])
    return [t for t in base if t not in CHAT_READ_ONLY_BLOCKLIST]


def tool_set(agent_id: str) -> list[str]:
    """Return the tool name allow-list for the growth agent.
    Includes graph mutations (register_node, link_nodes, infer_edges)
    plus the full read surface. The chat surface gets a read-only subset
    via chat_tool_set()."""

    return TOOL_SETS.get(agent_id, TOOL_SETS[DEFAULT_AGENT])


# ══════════════════════════════════════════════════════════════════════════════
# System prompts — loaded from each agent's system_prompt.md (canonical source)
# ══════════════════════════════════════════════════════════════════════════════

WORKSPACE_LAYOUT = """\
## Project layout (20260720 GraphRAG)
- assets/             source materials (papers, extractions, notebooks, infrastructure)
- general_tools/              SHARED runtime + tool suite for all agents (KGP, encoder, IPP,
                      engine, graph tools, codex 19 tools, audit tools)
- LLMs/               LLM backends (llm.py provider, grok) + .env credentials
- database/           note-based projects — THE knowledge store (see database/README.md)
- database/IPP.json      the database node (6 channels: project, nodes, edges, graph,
                         supplement, categories) — the note store as an IPP component
                      nodes & edges, references, VCL, export interactive)
- database/<project>/graph_data/   ALL generated artifacts of a project
                      (knowledge_graph.json · vectors/ · logs/ · interactive.html)
- ui/                 web control center + Gradio chat
- codex_growth/ codex_RAG/ codex_normal/   the three agents (tailored engines)
The knowledge graph stores nodes (subjects/papers/concepts) with typed edges.
Each node is also a Markdown note in database/<project>/nodes/ with a
Version Control Log at the bottom (every change appends an entry)."""

_PROMPT_CACHE: dict[str, str] = {}


def system_prompt(agent_id: str) -> str:
    """Load the agent's system prompt from its system_prompt.md file,
    appending the shared WORKSPACE_LAYOUT.  Cached on first call."""
    if agent_id not in _PROMPT_CACHE:
        path = Path(__file__).resolve().parent.parent / agent_id / "system_prompt.md"
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            text = f"You are {agent_id}, a Graph Knowledge Network agent."
        _PROMPT_CACHE[agent_id] = text.strip() + "\n\n" + WORKSPACE_LAYOUT
    return _PROMPT_CACHE[agent_id]


def prompt_file(agent_id: str) -> Path:
    """Path of the agent's editable system_prompt.md."""
    return Path(__file__).resolve().parent.parent / agent_id / "system_prompt.md"
