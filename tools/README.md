# tools/ — SHARED Runtime + Tool Suite (IPP)

## Purpose

This is the **shared brain of the project**: everything the three agents
(`codex_growth`, `codex_RAG`, `codex_normal`) and the UI need to operate.
After the 2026-08-02 flattening, the former `graph_network/` package was
dissolved INTO `tools/` — the graph runtime, encoder, IPP core, engine, agent
classes, build scripts, and every tool now live here.

## Modules

| Module | Formerly | Role |
|---|---|---|
| `config.py` | `graph_network/config.py` + tools shim | single `Config`: workspace, DeepSeek, guardrails, `.env` loader, Pushover + conda extras |
| `IPP.py` | `graph_network/ipp.py` | legacy IPP = (Input, Φ, Output); `BaseTool` 4-phase lifecycle; `ToolRegistry` |
| `IPP_runtime.py` | — | the IPP **v0.2.8** bridge: `verify_node()` (17 invariants), `tool_node()`, `construct_from_file()` |
| `graph.py` | `graph_network/graph.py` | `KnowledgeGraph` (KGP): nodes, typed §4.3a edges, depth-3 local graphs, PageRank, JSON persistence |
| `encoder.py` | `graph_network/encoder.py` | Encoder layer: chunk → embed → numpy vector index → hybrid search |
| `engine.py` | `graph_network/engine.py` | `AgentEngine` (IPP agentic loop) with `chat_stream()` + `run_with_trace()` |
| `agents.py` | `graph_network/agents.py` | `NodeAgent` (operate on a node) + `GrowthAgent` (recursive self-improvement) |
| `build.py` | `graph_network/build.py` | `build_graph()` seeds the network from `assets/`; `export_backward_compatible()` |
| `build_cy3.py` | — | `build_cy3_graph()` seeds the Calabi–Yau graph from `assets/20260806 CalabiYau3fold/`; `sync_project_assets()` (node↔file manifest) |
| `graph_tools.py` | `graph_network/tools.py` | graph IPP tools: `get_local_graph`, `search_nodes`, `read_node`, `register_node`, … |
| `codex_tools.py` | — (original codex suite) | the 19-tool flat suite (files, shell, search, agents, memory, web) |
| `checks.py` | — | read-only audit tools: `review_top_threats`, `standard_check`, `advanced_check` |
| `agent_specs.py` | — | per-agent tool sets, prompts, `WORKSPACE_LAYOUT`, chat read-only blocklist |
| `api.py` | — | the single composition point: `ensure_tools()`, `definitions_for()`, `execute_tool()` |

## Why the flatten?

Previously `graph_network/` held the core while `tools/` was just the tool
suite — a split that forced two import roots and confusing cross-imports
(`graph_network.engine` ←→ `tools.api`). Now the core lives WITH the tools:

- agents import: `from tools.engine import AgentEngine`, `from tools.graph import KnowledgeGraph`
- LLM lives in `LLMs/deepseek/provider.py` (DeepSeek provider, re-exported by `LLMs/api.py` and `LLMs/deepseek/__init__.py`)
- notes store lives in `database/notes.py` (`NoteStore`, `Note`, `VCLogEntry`)
- visuals live in `ui/visuals.py`

## Import notes (avoid cycles)

`tools/__init__.py` is **lazy (PEP 562)** — it does not import `tools.api` at
package-import time, so `import tools.config` from `database/notes.py` /
`database/database_tool/` / `LLMs/deepseek/` never triggers the
`api → database_tool → notes → config` cycle. Use `from tools.config import
Config` for the core and `from tools.api import …` for the dispatch surface.

## Public API

```python
from tools.api import ensure_tools, definitions_for, execute_tool
from tools.config import Config
from tools.graph import KnowledgeGraph
from tools.encoder import EncoderLayer
from tools.engine import AgentEngine
from tools.agents import NodeAgent, GrowthAgent
from tools.build import build_graph, export_backward_compatible
from tools.IPP_runtime import verify_node          # IPP v0.2.8 17 invariants

ensure_tools()                                   # register graph + db + audit tools
result = execute_tool("get_local_graph", {"node_id": "g_retrieval"}, ctx)
```

## IPP v0.2.8 runtime

The v0.2.8 formal model lives in the main `ipp/` package
(`ipp/IPP_constructor.py`, `ipp/IPP_executor.py`, …). `tools/IPP_runtime.py`
is the bridge from this suite:

```python
from tools.IPP_runtime import verify_node, tool_node, construct_from_file

failures = verify_node(node)        # [] == ALL 17 OK
node = construct_from_file("LLMs/ipp.json", bindings={"provider": llm})
```

## Tool Dispatch Flow

```
AI returns tool_call → chat_stream() loop → execute_tool(name, args, ctx)
    → ToolRegistry/TOOL_MAP → IPP lifecycle (resolve→validate→prepare→invoke)
    → ToolResult/string → fed back to the AI in the next API call
```
