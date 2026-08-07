# ⬡ Graph Knowledge Network for Agentic Work

A **self-contained, local-first knowledge-graph platform** for agentic research: papers and notebooks are ingested into a typed, directed knowledge graph where every node is also a Markdown note with a Version Control Log. Three shared codex agents operate the network, and a **Multi Agent social layer** (strictly wired with **IPP v0.2.8**) lets 20 personalities collaborate, chat, and work toward shared goals — all from one web control center.

![Graph Knowledge Network — control center](assets/screenshot-graphrag.png)

![Multi Agent — the social layer](assets/screenshot-multi-agent.png)

---

## What it is

- **Knowledge Graph** — typed nodes (papers, concepts, datasets, totals, open questions) with directed edges, built from source materials (`assets/`) and persisted to `graph_data/knowledge_graph.json` + a vector index (`encoder`).
- **Note database** — every node is a Markdown note in `database/<project>/nodes/` with YAML front-matter, `[[wikilinks]]`, and a **Version Control Log (VCL)** at the bottom; every mutation appends an entry.
- **GraphRAG** — the encoder layer retrieves relevant chunks for grounded agent answers; local graphs (depth-k) materialize the agent's working memory.
- **Three codex agents** — `codex_growth` (grow/improve the network), `codex_RAG` (ask/understand it), `codex_normal` (general purpose). All share one tool registry with per-agent tool surfaces.
- **IPP v0.2.8** — the Information Process Protocol: every computational component (LLMs, agents, tools, the portal) is an IPP node with declarative `ipp.json` files, guardrail envelopes (ι_pre → π → Ω → ι_post → ρ → τ*), hash-chained audits, and constructor-resolved topology. See `IPP_v0.2.8_Specification.md` and `ipp/`.
- **Multi Agent social layer** (`IPP_Social/`) — 20 Codex agents (each with its own IPP identity), agent cards with three properties (capacity, random property, constraints), shared goal folders + task Markdown files, a global chat board with addressing, the four formal A2A modes, a settings tab (streaming/concurrency/social-responder), and a conversation loop where agents reply to each other based on their social property.

---

## Quick start

```bash
# from the workspace root
pip install -r requirements.txt

# the web control center  → http://127.0.0.3:8000
python ui/server.py

# headless strict-IPP verification (43 nodes, 17 invariants, mini swarm)
python -m IPP_Social.integration_demo          # offline mock
python -m IPP_Social.integration_demo --live   # real DeepSeek
```

Set your DeepSeek key in `LLMs/.env` (`DEEPSEEK_API_KEY=sk-...`); without it the UI falls back to an offline `MockProvider`.

---

## The control center (`ui/`)

A Flask REST API + vanilla-JS SPA (no build step, no CDN beyond marked.js). Tabs:

| Tab | What it does |
|:---|:---|
| **Graph** | global / local (depth-k) view, SVG / Interactive / Mermaid, node detail drawer |
| **Search** | vector RAG over the encoder layer |
| **Agent** | the three shared codex agents with full foldable process + streaming |
| **Database** | note projects: create/open, edit notes with VCL, export graph → notes |
| **Runs** | the run log (VCL) |
| **🤝 Multi Agent** | top-level view — see below |

### Multi Agent view

- **Agent Stage** — one-column live status cards for the 20 agents; click one to watch its full foldable process (thinking / messages / tool calls + results) and final answer on the right.
- **Many Agents** — pick a goal folder (created in Data), write instructions, **Start the goal**, stop the team, select agents (pill toggles), instruct one agent directly.
- **Data** — goal folders as files: create a folder, browse goals/tasks, continue/delete, and **clear chat** (inter-agent or the whole board).
- **Settings** — **LLM streaming mode** (OFF by default → many agents run truly concurrently; ON for per-token streaming), max concurrent agents, social responder on/off, max reply rounds, max broadcast responders.
- **Right panels** — Agent Process (foldable, ChatGPT/Copilot style with timestamps + full final answer), Inter Agent Chat (`Alice [Alice -> Bob]`), Global Chat Board (`Alice [Alice -> agents]`, `User [User -> chat board]` + post input).

---

## The Multi Agent platform (`IPP_Social/`)

Strict IPP v0.2.8: one shared GraphContext 𝒢 with **43 IPP nodes** — the LLM node, the `social_activity` node (6 channels: card, profile, tasks, chat_board, events, a2a), 20× (engine + tools) nodes (one per Codex personality), and the `social_portal` node (5 channels: discover, command, monitor, swarm, settings).

| Piece | Description |
|:---|:---|
| `agents/` | the three agent properties: **capacity** (10-dim identity: math, physics, engineering, biology, genomics, reasoning, research, social, play, creativity), **random property** (10-dim {mean, variance} → momentary "mention"), **constraints** (x,y,z + resources, physically validated: world bounds, max step, non-negative); Agent Cards with cross-agent comments; the 20-agent JSON dataset |
| `task_manager/` | goals = folders, tasks = Markdown files with VCL; `social_database/goals/` |
| `chat_board/` | global chat board with addressing (`to_agent_id`) + inbox delivery (direct_message / broadcast) |
| `a2a/` | the four formal A2A modes: `sync` (declared, disabled), `async` (task-based), `stream` (event bus), `push` (chat-board scoped) |
| `events/` | streaming event bus (buffered + live `SocialStream`) |
| `swarm/` | per-agent IPP identity + `AgentRuntime` threads, `SwarmManager` (topology-enforced dispatch), `SwarmBus`, and the `SocialResponder` daemon (agents reply to inbox messages; broadcasts answered by ≤ `max_broadcast_responders` agents chosen by social score) |
| `portal/` | the portal node — discover/command/monitor/swarm/settings |
| `settings.py` | persisted platform settings (`social_database/settings.json`) |
| `integration.py` | `build_platform()` — assembles everything into ONE GraphContext 𝒢 |
| `integration_demo.py` | headless verification (43 nodes, 17 invariants, mini swarm) |

Every interaction flows through guardrail envelopes with hash-chained audits — the agents genuinely discover the social layer (the `social_*` tools sit at the top of their tool list), post to the board with addressing, and converse with each other.

---

## Project layout

```
20260720 GraphRAG/
├── assets/                  source materials (papers, notebooks, screenshots)
├── tools/                   SHARED runtime: graph, encoder, engine, IPP, tool registry,
│                            agent_specs (per-agent tool sets), build*, checks
├── LLMs/                    DeepSeek provider (+ Mock), the LLM IPP node, .env credentials
├── database/                note-based projects (nodes/*.md with VCL) + database_tool mutations
├── graph_data/              generated knowledge graph + vectors + logs
├── ipp/                     the IPP v0.2.8 core (file, ports, object, executor, constructor,
│                            registry, schema, verify — 17 invariants)
├── IPP_Social/              the Multi Agent social layer (agents, task_manager, chat_board,
│                            a2a, events, swarm, portal, settings, integration, agent_tools)
├── ManyAgents/              the 20 Codex agent copies (each: engine/ + tools/ + system_prompt)
├── ui/                      Flask control center + static SPA (app.js, multiagent.js)
├── codex_growth|RAG|normal/ the three shared codex agents
├── IPP_v0.2.8_Specification.md   the formal protocol spec
└── requirements.txt         python dependencies
```

---

## Verification

```bash
python verify_ipp.py                     # all IPP nodes: ALL 17 invariants + live pipelines
python -m IPP_Social.integration_demo    # 43 nodes, strict topology, mini 2-agent swarm
```

## License

See `LICENSE`.
