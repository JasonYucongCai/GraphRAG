# general_tools/ — SHARED Runtime + Tool Suite (IPP)

## Purpose

This is the **shared brain of the project**: everything the three agents
(`codex_growth`, `codex_RAG`, `codex_normal`) and the UI need to operate.
After the 2026-08-02 flattening, the former `graph_network/` package was
dissolved INTO `general_tools/` — the graph runtime, encoder, IPP core, engine, agent
classes, build scripts, and every tool now live here.

## Modules

| Module | Role |
|---|---|
| `config.py` | single `Config`: workspace, DeepSeek, guardrails, `.env` loader, Pushover + conda extras |
| `IPP.py` | legacy IPP = (Input, Φ, Output); `BaseTool` 4-phase lifecycle; `ToolRegistry` |
| `IPP_runtime.py` | the IPP **v0.2.8** bridge: `verify_node()` (17 invariants), `tool_node()`, `construct_from_file()` |
| **`IPP.json`** | ⭐ **THE TOOLS NODE (F-file, §IPP structure)** — 7 channels: invoke / list / describe / graph / encoder / build / check |
| **`IPP_object.py`** | Ω_k handlers (op-dispatch per channel over tools.impl) |
| **`IPP_executor.py`** | Ξ_k guardrails — audit records carry `op` + `tool` + `agent` |
| **`construct.py`** | Γ (`create_tools_node`) + the shared bridge (`bind_tools`, `tools_node()` singleton, live `current_graph/encoder/agents`) |
| **`impl.py`** | ⭐ the `impl_*` operations (dispatch, definitions, graph/encoder/build/check ops) — single source of truth, NO tools, NO IPP |
| **`bridge.py`** | `_delegate` — the ONLY tool→IPP seam (guardrail envelope) |
| `graph.py` | `KnowledgeGraph` (KGP): nodes, typed §4.3a edges, depth-3 local graphs, PageRank, JSON persistence |
| `encoder.py` | Encoder layer: chunk → embed → numpy vector index → hybrid search |
| `engine.py` | `AgentEngine` (IPP agentic loop) with `chat_stream()` + `run_with_trace()` |
| `agents.py` | `NodeAgent` (operate on a node) + `GrowthAgent` (recursive self-improvement) |
| `build.py` / `build_cy3.py` | `build_graph()` seeds from `assets/`; `build_cy3_graph()` seeds the Calabi–Yau graph; `export_backward_compatible()` |
| `graph_tools.py` | graph tool definitions: `get_local_graph`, `search_nodes`, `read_node`, `validate_graph`, `summarize_local` — each DELEGATES to the node (graph/encoder channels) |
| `codex_tools.py` | the 19-tool flat suite (files, shell, search, agents, memory, web) — executed by the invoke channel |
| `checks.py` | audit tool definitions: `review_top_threats`, `standard_check`, `advanced_check` — each DELEGATES to the node (check channel) |
| `agent_specs.py` | per-agent tool sets, prompts, `WORKSPACE_LAYOUT`, chat read-only blocklist |
| `api.py` | composition + registration ONLY: `ensure_tools()`; `definitions_for()`/`execute_tool()` delegate through the node (backward compat) |

## Why the flatten?

Previously `graph_network/` held the core while `general_tools/` was just the tool
suite — a split that forced two import roots and confusing cross-imports
(`graph_network.engine` ←→ `tools.api`). Now the core lives WITH the tools:

- agents import: `from general_tools.engine import AgentEngine`, `from general_tools.graph import KnowledgeGraph`
- LLM lives in `LLMs/deepseek/provider.py` (DeepSeek provider, re-exported by `LLMs/api.py` and `LLMs/deepseek/__init__.py`)
- notes store lives in `database/notes.py` (`NoteStore`, `Note`, `VCLogEntry`) — and is realized as the
  **`database` IPP node** (`database/IPP.json` + `IPP_object.py` + `IPP_executor.py` + `construct.py`);
  every `database_tool` tool delegates to the node's guardrail envelope
- the SHARED runtime lives in **`tools` as an IPP node** (see below) — every tool dispatch flows
  through its guardrail envelope with a hash-chained audit (op + tool + agent)
- visuals live in `ui/visuals.py`

## Import notes (avoid cycles)

`tools/__init__.py` is **lazy (PEP 562)** — it does not import `tools.api` at
package-import time, so `import general_tools.config` from `database/notes.py` /
`database/database_tool/` / `LLMs/deepseek/` never triggers the
`api → database_tool → notes → config` cycle. Use `from general_tools.config import
Config` for the core and `from general_tools.api import …` for the dispatch surface.

## Public API

```python
from general_tools.api import ensure_tools, definitions_for, execute_tool
from general_tools.config import Config
from general_tools.graph import KnowledgeGraph
from general_tools.encoder import EncoderLayer
from general_tools.engine import AgentEngine
from general_tools.agents import NodeAgent, GrowthAgent
from general_tools.build import build_graph, export_backward_compatible
from general_tools.IPP_runtime import verify_node          # IPP v0.2.8 17 invariants
from general_tools.construct import tools_node, bind_tools  # the tools IPP node
from database.construct import database_node       # the database IPP node

ensure_tools()                                   # register graph + db + audit tools
bind_tools(graph, encoder)                       # bind the shared runtime
result = execute_tool("get_local_graph", {"node_id": "g_retrieval"}, ctx)
result = execute_tool("register_node", {"node_id": "x1", "entryname": "…"}, ctx)
# ↑ every tool call flows through the tools node → (db tools) → database node
#   envelope + hash-chained audit at every hop
```

## IPP structure — the `tools` node

The SHARED runtime is an **IPP v0.2.8 node** (`node_id: "tools"`):

| Channel | Ops | What it is |
|---|---|---|
| `invoke` | `{tool, args, agent_id?}` | execute ANY registered tool — BaseTool 4-phase lifecycle via the ToolRegistry, then the flat codex suite |
| `list` | `{names?, round_index?}` | the tool JSON-Schemas the LLM sees (registry + flat, agent-tailored) |
| `describe` | `{tool}` | one tool's definition |
| `graph` | local · read · validate · summarize · stats · pagerank · registry | the agent's hands on the network |
| `encoder` | search_nodes · search · ingest · save | vector RAG (agents + web UI) |
| `build` | build · cy3 · export | graph seeding / rebuild / exports |
| `check` | review · standard · advanced | the READ-ONLY audit suite |

Layering (mirrors `database/database_tool/`):

```
LLM/agents → ToolRegistry → tool classes (graph_tools / checks / database_tool)
                          │  bridge._delegate(channel, op, args, ctx)
                          ▼
              tools node Ξ: ι_pre → π → Ω → ι_post → ρ → τ*   (+ hash-chain audit)
                          ▼
              tools.impl (dispatch / graph / encoder / build / check ops)
              graph.py · encoder.py · codex_tools.py · build*.py  (implementations)
```

`api.py` is composition + registration only (`execute_tool`/`definitions_for`
delegate through the node — the public names are unchanged). The per-agent
tools nodes (`codex_*_tools`, `ManyAgents/*`) enforce their `tool_names` ACL
and delegate the execution to the shared tools node; the platform registers
the tools node into its shared GraphContext 𝒢 (the 45th node) and the agent
tools nodes' invoke channel resolves its downstream edge to `tools.invoke`.

## Tool Dispatch Flow

```
AI returns tool_call → chat_stream() loop → execute_tool(name, args, ctx)
    → tools node invoke channel (guardrail envelope + audit)
    → ToolRegistry/impl dispatch → IPP lifecycle (resolve→validate→prepare→invoke)
    → (graph/check tools) → tools node graph/check channel
    → (database tools) → database node channel
    → ToolResult/string → fed back to the AI in the next API call
```

## IPP v0.2.8 runtime

The v0.2.8 formal model lives in the main `IPP/` package
(`IPP/IPP_constructor.py`, `IPP/IPP_executor.py`, …). `tools/IPP_runtime.py`
is the bridge from this suite:

```python
from general_tools.IPP_runtime import verify_node, tool_node, construct_from_file

failures = verify_node(node)        # [] == ALL 17 OK
node = construct_from_file("LLMs/IPP.json", bindings={"provider": llm})
```

## Tool Dispatch Flow

```
AI returns tool_call → chat_stream() loop → execute_tool(name, args, ctx)
    → tools node invoke channel (guardrail envelope + audit)
    → ToolRegistry/impl dispatch → IPP lifecycle (resolve→validate→prepare→invoke)
    → (graph/check tools) → tools node graph/check channel
    → (database tools) → database node channel
    → ToolResult/string → fed back to the AI in the next API call
```
