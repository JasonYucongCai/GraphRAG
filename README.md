# ⬡ Graph Knowledge Network for Agentic Work

A **self-contained, local-first knowledge-graph platform** for agentic research: papers and notebooks are ingested into a typed, directed knowledge graph where every node is also a Markdown note with a Version Control Log. Three shared codex agents operate the network, a **Multi Agent social layer** (strictly wired with **IPP v0.2.8**) lets 20 personalities collaborate, chat, and work toward shared goals, and a **Recursive Agent** portal chains agents that build increasingly capable successors — all from one web control center.

![Graph Knowledge Network — Control Center](assets/screenshot-controlcenter-20260809.png)

![Multi Agent — the social layer](assets/screenshot-multiagent-20260809.png)

![Recursive Agent — agent chain](assets/screenshot-recursiveagent-20260809.png)

---

## What it is

- **Knowledge Graph** — typed nodes (papers, concepts, datasets, totals, open questions) with directed edges, built from source materials (`assets/`) and persisted per project to `database/<project>/graph_data/knowledge_graph.json` + a vector index (`encoder`).
- **Note database** — every node is a Markdown note in `database/<project>/nodes/` with YAML front-matter, `[[wikilinks]]`, and a **Version Control Log (VCL)** at the bottom; every mutation appends an entry. The store itself is an **IPP v0.2.8 component** (`database/IPP.json` + Ω/Ξ/Γ) — every mutation flows through guardrail envelopes with hash-chained audits.
- **GraphRAG** — the encoder layer retrieves relevant chunks for grounded agent answers; local graphs (depth-k) materialize the agent's working memory.
- **Three codex agents** — `codex_growth` (grow/improve the network), `codex_RAG` (ask/understand it), `codex_normal` (general purpose). All share one tool registry with per-agent tool surfaces.
- **IPP v0.2.8** — the Information Process Protocol: every computational component (LLMs, agents, tools, the portal) is an IPP node with declarative `IPP.json` files, guardrail envelopes (ι_pre → π → Ω → ι_post → ρ → τ*), hash-chained audits, and constructor-resolved topology. See `IPP_v0.2.8_Specification.md` and `IPP/`.
- **Multi Agent social layer** (`IPP_Social/`) — 20 Codex agents (each with its own IPP identity), agent cards with three properties (capacity, random property, constraints), shared goal folders + task Markdown files, a global chat board with addressing, the four formal A2A modes, a settings tab (streaming/concurrency/social-responder), and a conversation loop where agents reply to each other based on their social property.
- **Recursive Agent** (`recursive_agents/`) — a chain of agents where each level builds the next more capable successor (A1→A2→A3→…), with live LLM chat, full trace inspection, construction reports, and diff views.

---

## Quick start

```bash
# from the workspace root
pip install -r requirements.txt

# the web control center  → http://127.0.0.3:8000
python ui/server.py

# headless strict-IPP verification (45 nodes, 17 invariants, database + tools nodes, mini swarm)
python -m IPP_Social.integration_demo          # offline mock
python -m IPP_Social.integration_demo --live   # real DeepSeek
```

Set your DeepSeek key in `LLMs/.env` (`DEEPSEEK_API_KEY=sk-...`); without it the UI falls back to an offline `MockProvider`.

---

## The control center (`ui/`)

A Flask REST API + vanilla-JS SPA (no build step, no CDN beyond marked.js). Three top-level portals:

| Portal | Tab | Description |
|:---|:---|:---|
| **🖥 Control Center** | Graph | global / local (depth-k) view, SVG / Interactive / Mermaid, node detail drawer |
| | Search | vector RAG over the encoder layer |
| | Agent | the three shared codex agents with full foldable process + streaming |
| | Database | note projects: create/open, edit notes with VCL, export graph → notes — all routed through the `database` IPP node |
| | Runs | the run log (VCL) |
| **🤝 Multi Agent** | Agent Stage | one-column live status cards for the 20 agents; click one to watch its full foldable process + final answer on the right |
| | Many Agents | pick a goal folder, write instructions, select agents (pill toggles + ✅ update team), **Start the goal**, stop, instruct one agent directly |
| | Data | goal folders as files: create, browse goals/tasks, continue/delete, clear chat |
| | Settings | LLM streaming mode, max concurrent agents, social responder on/off |
| | Right panels | Agent Process (foldable), Inter Agent Chat (`Alice [Alice -> Bob]`), Global Chat Board (`User [User -> chat board]` + post) |
| **🔄 Recursive Agent** | Chat | Gradio-style live conversation with any agent in the chain |
| | Agent Trace | full foldable process for the selected agent |
| | Construction Report | the construction output from the last agent build |
| | Diff View | compare two agents side by side |

---

## The Multi Agent platform (`IPP_Social/`)

Strict IPP v0.2.8: one shared GraphContext 𝒢 with **45 IPP nodes**.

```
IPP_Social/
├── IPP_Social_communication_tools/   ← a2a modes + global chat board
│   ├── IPP_Social_a2a_modes.py       sync/async/stream/push dispatch
│   ├── IPP_Social_a2a_push.py        per-agent inbox delivery
│   ├── IPP_Social_a2a_async_task.py  task-based A2A
│   ├── IPP_Social_a2a_stream.py      event bus subscription
│   ├── IPP_Social_a2a_sync.py        sync handoff (declared, disabled)
│   └── IPP_Social_chatboard_tool.py  global chat board with addressing
├── IPP_Social_services_tools/        ← social node + portal + tasks + events
│   ├── IPP_Social_services_ipp.json  the social_activity IPP node F-file
│   ├── IPP_Social_services_ipp_object.py   Ω handlers (card/profile/tasks/chat/events/a2a)
│   ├── IPP_Social_services_construct.py    Γ constructor
│   ├── IPP_Social_services_provision.py    generate 20-agent dataset
│   ├── IPP_Social_portal_tool_ipp.json     the social_portal IPP node F-file
│   ├── IPP_Social_portal_tool_object.py    portal Ω handlers (discover/command/monitor/swarm/settings)
│   ├── IPP_Social_portal_tool_construct.py portal Γ constructor
│   ├── IPP_Social_tasks_manager.py         goal + task CRUD
│   ├── IPP_Social_tasks_goals.py           goal folder management
│   ├── IPP_Social_tasks_tasks.py           task file management
│   └── IPP_Social_event_tool_bus.py        streaming event bus
├── social_database/                 ← all persistent data
├── integration.py                   ← build_platform() — one GraphContext 𝒢
├── integration_demo.py              ← headless verification
├── settings.py / paths.py / util.py / errors.py
└── README.md
```

The **agent identity** and **swarm runtime** live under `ManyAgents/`:

```
ManyAgents/
├── agent_management/        ← agent cards, capacity, constraints, dataset
│   ├── agent_card.py        AgentCard with comments + VCL
│   ├── capacity.py          10-dim identity vector
│   ├── constraints.py       physical state (x,y,z + resources, validated)
│   ├── random_property.py   10-dim mean/variance → momentary "mention"
│   └── dataset.py           load/save agent cards (social_database/cards/)
├── swarm/                   ← concurrent multi-agent runtime
│   ├── agent_ipp.py         per-agent IPP identity + construction
│   ├── runtime.py           AgentRuntime (task queue + worker thread)
│   ├── swarm.py             SwarmManager (orchestrate 20 runtimes)
│   ├── responder.py         SocialResponder daemon (conversation loop)
│   ├── bus.py               SwarmBus (in-memory event bus for SSE)
│   └── IPP_object.py        live chat_stream handler
└── Codex_01_Alice/ … Codex_20_Vivian/  ← the 20 agent folders
```

---

## Project layout

```
20260720 GraphRAG/
├── assets/                  source materials (papers, notebooks, screenshots)
├── general_tools/           SHARED runtime — tools IPP node (26 channels)
│   │                        routes.py = R*_k, catalog.py = F-file defs,
│   │                        impl.py = domain ops; no BaseTool layer
├── LLMs/                    DeepSeek provider (+ Mock), LLM IPP node
├── database/                ⭐ knowledge store — database IPP node (6 channels)
│   ├── README.md            complete layout spec
│   └── <project>/           one folder per project:
│       ├── nodes/*.md       ⭐ source of truth (one note per node, VCL)
│       ├── supplement/      opt-in graph overlays
│       └── graph_data/      generated: knowledge_graph.json, vectors/, export/
├── IPP/                     IPP v0.2.8 core (file, ports, object, executor,
│                            constructor, registry, schema, verify)
├── IPP_Social/              Multi Agent social layer (communications + services)
├── ManyAgents/              20 Codex agents + agent_management + swarm runtime
├── recursive_agents/        Recursive agent chain (A1→A2→A3→…)
├── ui/                      Flask control center + static SPA
├── codex_growth|RAG|normal/ the three shared codex agents
├── IPP_v0.2.8_Specification.md   formal protocol spec
└── requirements.txt         python dependencies
```

---

## Verification

```bash
python verify_IPP.py                     # all IPP nodes: 17 invariants + live pipelines
python -m IPP_Social.integration_demo    # 45 nodes, database + tools nodes, mini swarm
python server_smoke.py                   # /api/database/* endpoints through node
```

## License

See `LICENSE`.

---

# Appendix A — IPP v0.2.8 Architecture Reference

## A.1 The Guardrail Envelope (ι_pre → π → Ω → ι_post → ρ → τ*)

Every computational component is an **IPP node** declared in an
`IPP.json` F-file. When a channel is invoked (`node.invoke(channel,
payload)`), the call flows through a guardrail envelope:

```
ι_pre   → validate payload against the channel's input schema (O1 conformance)
         → if invalid: escalate to error-handling fallback, stop
π       → policy check (rate limit, cost cap, security clearance)
Ω       → the handler function (Ω_k) — executes the actual logic
ι_post  → validate output against the channel's output schema (O2 conformance)
ρ       → provenance: hash-chain the audit record (SHA-256)
τ*      → topology routing: resolve the downstream target (constructor-resolved)
```

Each step is recorded in an **audit record** appended to a JSONL log file
(e.g. `graph_data/logs/IPP/social_portal.command.jsonl`). The records
are hash-chained: each record's hash includes the previous record's hash,
forming an append-only immutable audit trail (Axiom X3).

## A.2 The Shared GraphContext 𝒢

All 45 IPP nodes are registered in ONE `GraphContext` instance. Node
resolution is **constructor-resolved**: edges between nodes are computed
by the Γ constructor from the IPP.json declarations, NOT manually wired.

```
𝒢 = GraphContext()
  ├── llm                    ← LLMs/IPP.json (chat, complete, chat_stream)
  ├── social_activity        ← IPP_Social_services_ipp.json (6 channels)
  ├── database               ← database/IPP.json (6 channels)
  ├── tools                  ← general_tools/IPP.json (26 channels)
  ├── social_portal          ← IPP_Social_portal_tool_ipp.json (5 channels)
  ├── Codex_01_Alice_engine  ← ManyAgents/Codex_01_Alice/engine/IPP.json
  ├── Codex_01_Alice_tools   ← ManyAgents/Codex_01_Alice/tools/IPP.json
  ├── ... (18 more agents × 2 nodes each)
  ├── Codex_20_Vivian_engine
  └── Codex_20_Vivian_tools
```

The per-agent tools node's `invoke` channel resolves its downstream edge
to the SHARED `tools.invoke` channel — one execution plane, one audit
trail, per-agent ACL enforcement.

## A.3 The Tool Routing System (R*_k)

Every agent-callable tool name maps to a target channel's guardrail
envelope through `general_tools/routes.py`. The routing table has three
target categories:

| Route target | Description | Example tools |
|:---|:---|:---|
| `self` | A channel of the tools node itself | `shell_command`, `read_file`, `get_local_graph`, `search_nodes` |
| `database` | The database IPP node | `register_node`, `link_nodes`, `create_project` |
| `social_activity` | The social IPP node | `social_post`, `social_board`, `social_inbox`, `social_agents` |

The route tuple is `(node_key, channel, op, adapter)`:
- `node_key`: `"self"`, `"database"`, or `"social_activity"`
- `channel`: the target node's channel (e.g. `"invoke"`, `"chat_board"`, `"nodes"`)
- `op`: the operation discriminator (e.g. `"post"`, `"register"`, `"local"`)
- `adapter`: optional function that remaps LLM function-call arguments to the channel's op schema

**The tool definitions the LLM sees** are derived from the F-file channel
input schemas (via `anyOf` per-op branches) — there is NO separate
BaseTool layer. The catalog is built once at construction time by
`general_tools/catalog.py`.

## A.4 Tool Execution Flow (End-to-End)

When an LLM calls a tool:

```
1. LLM emits function_call {name: "social_post", arguments: {text: "Hi", to_agent_id: "Codex_01_Alice"}}
2. AgentEngine._dispatch_tool("social_post", args, ctx)
3. tools_node.invoke("invoke", {tool: "social_post", args: {...}, agent_id: "Codex_04_Fiona"})
4. impl_execute_tool() looks up ROUTES["social_post"]
   → ("social_activity", "chat_board", "post", _social_post)
5. Adapter _social_post remaps: {op: "post", author_agent_id: "Codex_04_Fiona", text: "Hi", to_agent_id: "Codex_01_Alice"}
6. _target_node("social_activity", "chat_board", "post", payload)
   → social_node.invoke("chat_board", payload)
7. chat.post("Codex_04_Fiona", "Hi", to_agent_id="Codex_01_Alice")
8. Board writes to JSONL, delivers push notification to Alice's inbox
9. Result flows back through the guardrail envelope:
   → content extraction by _serialize_social_result()
   → returned to LLM as tool_result message
```

## A.5 Content Serialization for LLM Context

`_serialize_social_result()` in `general_tools/impl.py` converts raw API
responses into formatted text the LLM can understand:

- **`messages`** → `🌐 GLOBAL CHAT BOARD` with `[timestamp] sender → target: text #tags`
  - 👤 USER messages are pinned at top under `📌 MESSAGES FROM THE HUMAN OPERATOR`
  - Agent messages follow in `📋 RECENT BOARD` section
- **`cards`** → `👥 REGISTERED AGENTS` with agent_id: name
- **`inbox`** → `📬 YOUR INBOX` with sender, kind, and message text
- **`goals`** → `🎯 GOALS` with status and task counts
- Empty results → `"(board is empty)"` instead of bare `"ok"`

## A.6 The Conversation Loop (SocialResponder)

The `SocialResponder` daemon in `ManyAgents/swarm/responder.py` polls
agent inboxes every 3 seconds and enqueues reply tasks:

1. Check if responder is enabled (`social_responder` setting)
2. For each IDLE agent (not running, queue empty):
   - Read inbox via `social_node.invoke("a2a", {mode: "push", action: "inbox"})`
   - Skip already-seen messages, self-authored messages, system posts (tags: swarm/done/system)
   - **Direct messages** (kind="direct_message"): always enqueue reply
   - **Broadcasts** (kind="broadcast"): reply if social score roll passes (≤ `max_broadcast_responders` per message)
   - **User board posts** (kind="board_broadcast"): reply if social score roll passes
   - Conversation depth capped at `max_reply_rounds` per (author, agent) pair
3. Reply instruction tells the agent WHO to reply to and HOW:
   ```
   [SOCIAL REPLY 1/2] Codex_08_Julia (Codex_08_Julia) sent YOU a direct message:
   "Hey Fiona! ..."
   Reply to Codex_08_Julia personally with social_post to='Codex_08_Julia'.
   One short sentence is enough.
   ```

## A.7 Message Addressing Protocol

The chat board supports three addressing modes via `to_agent_id`:

| `to_agent_id` | Delivery | Inbox kind | Display in UI |
|:---|:---|:---|:---|
| `""` / `"chat_board"` | Every agent's inbox | `board_broadcast` | `User [User -> chat board]` |
| `"agents"` | Every agent's inbox (excl. author) | `broadcast` | `Alice [Alice -> agents]` |
| `"Codex_01_Alice"` | Single agent's inbox | `direct_message` | `Catherine [Catherine -> Alice]` |

User posts to the board go through the portal's `command.board` op, which
invokes `social_node.invoke("chat_board", {op: "post", author: "user", ...})`.
The `"user"` author is exempt from the agent-card requirement so the human
operator can post without being a registered agent.

## A.8 Health & Verification

```bash
# Full IPP verification (17 invariants per node × 5 node types):
python verify_IPP.py

# Multi Agent platform integration test:
python -m IPP_Social.integration_demo          # offline MockProvider
python -m IPP_Social.integration_demo --live   # real DeepSeek API

# The demo covers:
#   45 nodes in 𝒢, 17 invariants, database node CRUD,
#   tools node dispatch + catalog, social_post/social_board routing,
#   mini swarm (2 agents with MockProvider)
```

---

# Appendix B — Data Flow & Persistence

## B.1 Social Database Structure

```
IPP_Social/social_database/
├── cards/                          ← agent cards (one JSON per agent)
│   ├── Codex_01_Alice.json         {agent_id, name, capacity, random_property, constraints, vcl}
│   ├── Codex_02_Catherine.json
│   ├── ... (20 agents)
│   └── user.json                   ← the human operator's card
├── goals/                          ← shared goal folders
│   └── <goal_id>/
│       ├── goal.md                 ← goal metadata (YAML front-matter)
│       └── tasks/
│           └── <task_id>.md        ← individual task (YAML + VCL)
├── chat/
│   └── board.jsonl                 ← global chat board (append-only JSONL)
├── events/
│   └── events.jsonl                ← event bus (append-only JSONL)
├── push/
│   ├── subscriptions.json          ← push subscriber list
│   └── <agent_id>/
│       └── inbox.jsonl             ← per-agent message inbox (JSONL)
└── settings.json                   ← platform settings (JSON)
```

## B.2 Settings Persistence

Platform settings at `social_database/settings.json`:

```json
{
  "llm_streaming": false,
  "max_concurrent": 4,
  "social_responder": true,
  "max_reply_rounds": 2,
  "max_broadcast_responders": 4
}
```

| Setting | Default | Effect |
|:---|:---|:---|
| `llm_streaming` | `false` | `true` = per-token HTTP streaming (best for 1 agent); `false` = single non-streaming completion (concurrent-friendly) |
| `max_concurrent` | `4` | How many AgentRuntime threads may hold the shared semaphore simultaneously |
| `social_responder` | `true` | Whether the SocialResponder daemon polls inboxes and enqueues replies |
| `max_reply_rounds` | `2` | Max conversation depth per (author, agent) pair |
| `max_broadcast_responders` | `4` | Max agents that may answer a single broadcast message |

## B.3 Error Domain

All social-layer errors extend `SocialError` and produce structured payloads:

```python
{"ok": false, "error": "<code>", "message": "<human text>", ...extra_fields}
```

| Error code | Class | Trigger |
|:---|:---|:---|
| `bad_request` | SocialError | Missing required fields (`post requires author_agent_id + text`) |
| `unknown_agent` | UnknownAgent | Referenced agent not in the dataset |
| `duplicate_agent` | DuplicateAgent | Registering an agent that already exists without `overwrite` |
| `constraint_violation` | ConstraintViolation | Physical constraint check failed (world bounds, max step, non-negative) |
| `mode_not_allowed` | ModeNotAllowed | Calling a declared-but-disabled A2A mode (sync) |
| `push_scope_denied` | SocialError | Push target outside allowed scopes |
| `unknown_goal` | UnknownGoal | Referenced goal_id not found |
| `unknown_task` | UnknownTask | Referenced task_id not found |
| `invalid_status` | InvalidStatus | Task status transition not in submitted→processing→done/failed |
