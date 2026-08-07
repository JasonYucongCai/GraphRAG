# IPP_Social — the Multi Agent social layer (strict IPP v0.2.8)

One platform, one shared GraphContext 𝒢, 43 IPP nodes: the LLM, the
`social_activity` node (Agent Cards, 3 properties, goals/tasks, chat
board, event bus, four A2A modes), the 20 ManyAgents Codex agents (each
with its own engine + tools node), and the `social_portal` node that the
web UI talks to.

```
ui/static/multiagent.js ── HTTP/SSE ──► ui/server.py ──► social_portal (IPP node)
                                                           │  Γ-resolved τ*_k
                        ┌──────────────────────────────────┼───────────────────┐
                        ▼ (discover/command/monitor)        ▼ (swarm, multicast)
                social_activity ───────────► 20 × Codex_XX engine nodes
                (cards, tasks, board,        (chat_stream — live per-step
                 events, a2a)                 events through the envelope)
                        ▲                                      │
                        └────── task completion + board posts ─┘
```

## The modules

| folder | what it is |
|:---|:---|
| `agents/` | the 3 properties (capacity, random property, constraints), Agent Card, and the 20-agent JSON dataset |
| `task_manager/` | shared goal folders + task Markdown files (VCL at bottom) |
| `chat_board/` | the global chat board (+ push fan-out) |
| `events/` | the streaming event bus (buffered + live `SocialStream`) |
| `a2a/` | the four formal A2A modes: sync (declared, disabled), async, stream, push (chat-board scoped) |
| `swarm/` | the concurrent multi-agent runtime: per-agent IPP identity (`agent_ipp.py`), the live streaming handler (`IPP_object.py`), `AgentRuntime` worker threads, `SwarmManager`, in-memory `SwarmBus` |
| `portal/` | the `social_portal` IPP node: discover / command / monitor / swarm |
| `social_database/` | the data-only social database (goals, chat, events, push) |
| `integration.py` | `build_platform()` — assembles everything into ONE GraphContext 𝒢 |
| `integration_demo.py` | headless verification (`python -m IPP_Social.integration_demo`) |

## Strict IPP v0.2.8 wiring

- **One 𝒢**: the LLM node, social_activity, all 20 agents' engine+tools
  nodes and the portal node are constructed through Γ into a single
  `GraphContext` (43 registered nodes).
- **Per-agent identity**: each ManyAgents copy's `engine/ipp.json` +
  `tools/ipp.json` are finalized with its own `node_id`
  (`Codex_01_Alice_engine` …), its own handler refs
  (`ManyAgents.<agent>.engine.IPP_object:…`), and its own audit log
  endpoints — no two nodes share an identity.
- **Constructor-resolved topology**: the portal's `command`/`discover`
  channels resolve their downstream to `social_activity`'s SocialOp
  channels; the `swarm` channel resolves to the 20 engine nodes'
  `ground`/`chat_stream` channels (exact logical-type matching) — and
  `SwarmManager.start` refuses agents outside that resolved set
  (Axiom X5 conformance).
- **Everything through guardrail envelopes**: portal → social (goals,
  tasks, board posts), portal → agent engines (`chat_stream` with a
  live `context["on_event"]` pushing each thinking/tool/message step to
  the swarm bus), agents → social (task completion + board broadcast).
  Every channel is audited with hash-chained records (Axiom X3).

## The web portal (ui)

- The **brand title is now a clickable button** back to the original
  Graph portal.
- The new **Multi Agent tab**: left sidebar lists the 20 agents with
  avatars + status dots; name a goal and give instructions to the whole
  team (or select specific agents); instruct one agent directly; browse
  goals. The main canvas shows **mini agent boxes** — each agent's live
  thinking/tool calls — plus the activity stream, fed over SSE from the
  swarm bus.
- API: `/api/social/agents`, `/api/social/goals`, `/api/social/goal`,
  `/api/social/instruct`, `/api/swarm/start|stop|status`,
  `/api/swarm/events` (SSE).

## Run

```bash
python ui/server.py                     # control center → 127.0.0.3:8000
python -m IPP_Social.integration_demo   # headless strict-IPP verification
python -m IPP_Social.integration_demo --live   # with the real DeepSeek provider
```
