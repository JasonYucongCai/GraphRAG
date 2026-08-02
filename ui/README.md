# ui/ — Graph Knowledge Network Control Center

A self-contained web interface (Flask REST API + vanilla-JS SPA) for the graph
knowledge network. No build step, no CDN dependencies — everything serves from
`ui/static/`.

## Run

```bash
# from the workspace root
python ui/server.py                     # → http://127.0.0.3:8000
python ui/server.py --port 5000         # → http://127.0.0.3:5000
python ui/server.py --host 127.0.0.1    # → http://127.0.0.1:8000
```

The server auto-loads the persisted graph from `graph_data/` or builds it from
`assets/` on first start. The DeepSeek provider is live if the API key is
configured (`LLMs/.env`), otherwise an offline `MockProvider` keeps the UI
functional.

The **Agent tab** of the main control center runs the three shared codex agents
directly (agent dropdown + anchor node + task): `codex_normal` (general),
`codex_RAG` (ask the network) and `codex_growth` (improve notes / expand the
network) — via the unified `POST /api/agent/chat` endpoint.

**Foldable agentic process**: the response shows the ENTIRE process —
thinking (🧠), messages (💬), tool calls (🛠) and tool results (↩), each in its
own collapsible block (like ChatGPT/Copilot) — followed by the **full final
answer** in a scrollable box. Nothing is truncated.

**True streaming**: the Agent tab consumes `POST /api/agent/chat/stream`
(Server-Sent Events) and renders every event AS IT HAPPENS — thinking deltas,
message text streaming word-by-word, tool calls appearing when invoked, and the
final answer growing progressively. No more "stuck then dump".

**Read-only chat**: the chat surface uses `chat_mode=True`, which COMMENTED
OUT the file-write tools (`write_file`, `apply_patch`, `shell_command`) and the
graph-mutation tools (register/link/delete/append_vcl/…). The chat can read,
search and audit — it cannot write files or mutate the graph. The growth agent
still owns mutations in its full-power mode.

## Gradio Chat (`ui/gradio_chat.py`)

The traditional chat interface for the three agents (same engines, same
read-only chat_mode + foldable process):

```bash
python ui/gradio_chat.py                 # → http://127.0.0.3:7860 (choose agent in the UI)
python ui/gradio_chat.py --agent codex_RAG
python codex_normal/chat.py              # → same app, default = codex_normal
```

- `codex_normal` — general tasks (files, shell, search, sub-agents, memory, web) + audits
- `codex_RAG` — ask questions about the knowledge network (anchor node + question)
- `codex_growth` — improve a node note / expand the network (anchor node + instruction)

The answer renders as a foldable `<details>` "🔄 Agentic process" (nested
thinking/message/tool blocks) followed by `---` and the final answer. The chat
supports an **anchor node** field that binds the agent to a node's depth-3
local graph.

## Audit tools (in the agentic chat)

| Tool | Purpose |
|---|---|
| `review_top_threats` | scan for top security threats (exposed keys, dangerous patterns) |
| `standard_check` | structure / syntax / graph consistency |
| `advanced_check` | large files, `.env` exposure, TODOs, dependency pins |

All audit tools are read-only (they only grep/read files and the graph).

## REST API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | provider, tools, agents, workspace |
| GET | `/api/agent/list` | the three codex agents + tool counts |
| POST | `/api/agent/chat` | unified agent chat: `{agent, node, task}` |
| POST | `/api/agent/chat/stream` | STREAMING agent chat (SSE): same body, emits each event as it happens |
| GET | `/api/graph/summary` | stats, pagerank top, registry (backward-compatible) |
| GET | `/api/graph/nodes` | all nodes with degrees + pagerank |
| GET | `/api/graph/node/<id>` | node detail + incoming/outgoing edges |
| GET | `/api/graph/local/<id>?depth=3` | depth-k ego network (visualization payload) |
| GET | `/api/graph/edges` | all edges of the global graph |
| GET | `/api/visual/interactive?node=&depth=` | PyVis-style interactive HTML (vis-network) |
| GET | `/api/visual/mermaid?node=&depth=` | Mermaid `graph LR` dependency flowchart |
| POST | `/api/search` | vector RAG: `{query, k}` → nodes + chunks |
| POST | `/api/agent/node` | run NodeAgent: `{node, task}` |
| POST | `/api/agent/grow` | run GrowthAgent: `{node, topic, motivation}` |
| GET | `/api/database/projects` | list note projects + current |
| POST | `/api/database/create` | `{name, description}` → new project |
| POST | `/api/database/open` | `{name}` → load notes into the live graph |
| GET | `/api/database/notes` · `/api/database/note/<id>` | note list · raw note |
| POST | `/api/database/sync` | export graph nodes → `.md` notes (idempotent) |
| POST | `/api/database/note/update` | save note content + append VCL entry |
| GET | `/api/runs` | VCL run log |
| GET | `/api/export` | backward-compatible export info |
| POST | `/api/graph/rebuild` | rebuild graph from `assets/` |

## Frontend

`static/index.html` · `static/style.css` · `static/app.js` — a dark-theme SPA
with:

- **Graph tab** — live stats, searchable node list, force-directed SVG
  visualization of the **entire global graph** or any node's local graph
  (depth 1–4), click any node for a detail drawer (metadata + in/out edges)
- **Visualization modes** — toggle between `SVG` (custom force-directed with
  drag/pan/zoom), `Interactive` (PyVis-style vis-network with physics,
  tooltips, and a `database/<project>/interactive.html` export), and
  `Mermaid` (the `graph LR` dependency-flowchart format used by the
  ScientificInfrastructure notebooks)
- **Search tab** — vector RAG over the encoder layer (nodes + grounded chunks
  with similarity scores)
- **Agent tab** — run the Node agent on any node's local graph, or the Growth
  agent to expand the network (dedup + limits + consistency enforced)
- **Database tab** — create/open note projects (one `.md` per node with a
  Version Control Log), export the graph to notes, edit notes and append VCL
  entries
- **Runs tab** — the version-control run log (VCL)

### Canvas interactions

- **Drag nodes** — click and hold a node, move it anywhere
- **Pan** — drag on empty background
- **Zoom** — mouse wheel (centered on cursor)
- **Focus** — double-click a node to zoom into it; double-click empty space to reset the view
- **Details panel** — the `☰ details` button toggles the node drawer; the
  drawer is a *flex sibling* of the canvas, so it never covers the graph, and
  it can always be reopened after closing

The force-directed layout, category colors, and interactions are implemented in
plain JS — no external libraries.
