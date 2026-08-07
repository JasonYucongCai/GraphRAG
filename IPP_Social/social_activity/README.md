# social_activity — plug-and-play IPP v0.2.8 social component

A single IPP node (node_id **`social_activity`**) that the `ManyAgents`
Codex agents connect to **through IPP**. It gives every agent a social
identity, a shared workspace to collaborate on goals, a global chat
board, a streaming event bus, and the four formal A2A interaction modes.

```
IPP_Social/
├── agents/                  # THE THREE PROPERTIES + AGENT CARD  (module)
│   ├── capacity.py          #   property 1 — 10-dim identity scores
│   ├── random_property.py   #   property 2 — 10-dim {mean, variance} vector
│   ├── constraints.py       #   property 3 — mutable physical vector (x,y,z+resources)
│   ├── agent_card.py        #   the Agent Card (discovery + cross-agent comments)
│   ├── dataset.py           #   dataset I/O (one JSON per agent)
│   └── dataset/             #   THE DATASET — 20 JSON files (Codex_01_Alice.json …)
├── task_manager/            # SHARED TASK MANAGEMENT  (module)
│   ├── goals.py             #   a goal is a folder
│   ├── tasks.py             #   individual tasks are Markdown files (VCL at bottom)
│   └── manager.py           #   TaskManagement facade
├── chat_board/              # GLOBAL CHAT BOARD  (module)
│   └── board.py             #   post / get / get_since + push fan-out
├── events/                  # STREAMING EVENT BUS  (module)
│   └── bus.py               #   append-only events.jsonl + live SocialStream
├── a2a/                     # THE FOUR FORMAL A2A MODES  (module)
│   ├── modes.py             #   the formal method registry + dispatcher
│   ├── sync.py              #   SyncHandoff        (declared, NOT allowed)
│   ├── async_task.py        #   AsyncTask          (allowed — submit + poll)
│   ├── stream.py            #   StreamSubscription (allowed — event bus)
│   └── push.py              #   PushNotification   (allowed — chat board only)
├── social_database/         # THE SOCIAL DATABASE  (data only)
│   ├── goals/<goal_id>/     #   actual goals: goal.md + tasks/<task_id>.md
│   ├── chat/board.jsonl     #   global chat board
│   ├── events/events.jsonl  #   event bus
│   └── push/                #   subscriptions.json + <agent>/inbox.jsonl
├── errors.py  paths.py  util.py
└── social_activity/         # THE PLUG-AND-PLAY IPP COMPONENT  (node)
    ├── ipp.json             #   F — 6-channel node declaration
    ├── IPP_object.py        #   Ω handler factories
    ├── IPP_executor.py      #   Ξ executor classes
    ├── construct.py         #   Γ helper (build_social_components/create_social_node)
    ├── __init__.py          #   SocialActivity facade
    ├── provision.py         #   generate the 20-agent dataset from ManyAgents
    ├── demo.py              #   end-to-end verification
    └── README.md
```

## The three agent properties

Every agent carries exactly three properties, registered on its Agent Card:

| Property | Meaning | Mutability |
|:---|:---|:---|
| **capacity** | the *identity* of what the agent can do — a 10-dimensional score vector (0–100): `math, physics, engineering, biology, genomics, reasoning, research, social, play, creativity` | fixed at registration (identity) |
| **random property** | a 10-dimensional stochastic trait vector; each dimension is `{mean, variance}` and *sampling* it yields the agent's momentary tendency ("mention"): `N(mean, √variance)` clamped to [0, 100] | fixed at registration (identity) |
| **constraints** | the mutable physical state vector: position `(x, y, z)` plus additional resources. Every update obeys the physical constraints: world bounds `[0, 100]`, max step `10` per axis per update (no teleporting), non-negative resources | **mutable** via `profile.update_constraints` (validated) |

## The social artifacts

1. **Agent Card** (`agents/` + `agents/dataset/*.json`) — the discovery
   surface. Each agent is **one JSON file** holding the three properties
   plus discovery metadata and comments. Any agent can `register`, `get`,
   `list`. Cards are **editable by other agents**: `comment` appends an
   annotation (author, text, ts), bumps the card version, and logs to the
   card's VCL. Capacity is identity — comments are the only cross-agent
   edit channel.
2. **Shared task management** (`task_manager/` + `social_database/goals/`)
   — a *goal is a folder*; its *individual tasks are Markdown files*
   inside it (`goals/<goal_id>/tasks/<task_id>.md`), each with a
   **Version Control Log at the bottom** (repo convention). Any agent may
   create goals, create/update tasks (status, notes, reassignment) —
   collaboration toward making the goal true.
3. **Global chat board** (`chat_board/` + `social_database/chat/`) — one
   shared board; a `post` is broadcast to every agent.
4. **Streaming event bus** (`events/` + `social_database/events/`) —
   append-only event log (`agent_joined, card_commented,
   constraints_updated, goal_created, task_created, task_updated,
   message_posted, push_*`). Buffered by default; `live: true` returns a
   live iterator.

## The four formal A2A interaction modes (A2A by Google)

All four are **coded as formal methods** on the `a2a` channel (registry in
`a2a/modes.py`); enforcement is per-method:

| mode | method | semantics | currently |
|:---|:---|:---|:---|
| `sync` | `SyncHandoff` | send the entire info, receive the entire response (handoff) | **declared, NOT allowed** → `mode_not_allowed` |
| `async` | `AsyncTask` | submit a task into a goal folder; poll it; each poll responds with the task's current status | **allowed** |
| `stream` | `StreamSubscription` | subscribe to the social event bus (buffered or live) | **allowed** |
| `push` | `PushNotification` | notification delivery without polling | **allowed, chat board only** — any other target → `push_scope_denied` |

Push fan-out: when a chat-board post succeeds, every subscriber's inbox
(`social_database/push/<agent>/inbox.jsonl`) receives the notification —
the chat board is currently the **only** push source.

## Channels & ops

| channel | op | purpose |
|:---|:---|:---|
| `card` | `register` `get` `list` `comment` | Agent Card lifecycle, discovery, cross-agent comments |
| `profile` | `get` `update_constraints` | the three properties; physical constraints update |
| `tasks` | `create_goal` `list_goals` `get_goal` `create_task` `update_task` `get_task` `list_tasks` | shared goal/task collaboration |
| `chat_board` | `post` `get` `get_since` | global chat board (+ push fan-out) |
| `events` | `{since?, live?, timeout_s?}` | streaming event bus |
| `a2a` | `{mode: sync\|async\|stream\|push, …}` | the four formal A2A modes |

## Plug & play

```python
import sys; sys.path.insert(0, r"D:\Deepin\Programming\20260720 GraphRAG")
from IPP_Social.social_activity import SocialActivity

social = SocialActivity()                       # builds the IPP node + modules

# 1) connect ManyAgents — generate the 20-agent dataset
from IPP_Social.social_activity.provision import provision_many_agents
provision_many_agents(social.dataset)           # → agents/dataset/*.json (20 files)

# 2) use the IPP surface directly
social.invoke("card", {"op": "get", "agent_id": "Codex_16_Ruby"})
social.invoke("a2a", {"mode": "async", "action": "submit",
                      "from_agent_id": "Codex_01_Alice",
                      "goal_id": "my-goal", "message": "please check"})
```

Or the facade methods (`social.register_agent(...)`, `social.discover()`,
`social.create_goal(...)`, `social.post_message(...)`, `social.a2a(...)`,
…). Everything flows through the IPP guardrail envelope
(ι_pre → π → Ω → ι_post → ρ → τ*), with hash-chained audit records per
channel and no bypass path.

## Verification

```bash
python -m IPP_Social.social_activity.demo          # full end-to-end demo (temp db)
python -m IPP_Social.social_activity.provision --list   # generate + list dataset
```

The demo asserts **ALL 17 IPP invariants** (`verify_node` → `[]`), every
channel's audit hash chain, and all four A2A modes. To wire the node into
a shared GraphContext (external topology), construct with an existing
context and register the node:

```python
from ipp.IPP_registry import GraphContext
from IPP_Social.social_activity import create_social_node
ctx = GraphContext()
node, comps = create_social_node(context=ctx)     # Γ resolves + registers
```

## Status / roadmap

- [x] module folders: `agents/` (3 properties + card + dataset),
      `task_manager/`, `chat_board/`, `events/`, `a2a/`
- [x] social database: `social_database/{goals,chat,events,push}`
- [x] 20-agent dataset as JSON files (`agents/dataset/`)
- [x] Agent Cards + cross-agent comments, 3 properties, physical constraints
- [x] goal folders + markdown tasks with VCL, chat board, event bus
- [x] four formal A2A modes (sync declared-disabled; async + stream on;
      push chat-board scoped)
- [x] 6-channel IPP node, handlers, executors, constructor, facade
- [ ] wire the Codex agents' IPP nodes to `social_activity` in one
      GraphContext (external topology resolution)
- [ ] enable `sync` handoff when a handoff executor is deployed
- [ ] portal / UI integration
