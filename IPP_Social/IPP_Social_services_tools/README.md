# IPP_Social_services_tools — social node + portal + tasks + events

Merged from the former `social_activity/`, `portal/`, `task_manager/`,
and `events/` sub-packages in the August 2026 IPP_Social restructure.
This folder contains the two core IPP nodes (`social_activity` and
`social_portal`) plus the task management and event bus infrastructure.

```
IPP_Social_services_tools/
├── IPP_Social_services_ipp.json          # social_activity F-file
├── IPP_Social_services_ipp_object.py     # social_activity Ω handlers
├── IPP_Social_services_ipp_executor.py   # social_activity Ξ executor
├── IPP_Social_services_construct.py      # social_activity Γ constructor
├── IPP_Social_services_provision.py      # 20-agent dataset generator
├── IPP_Social_services_demo.py           # standalone demo
├── IPP_Social_portal_tool_ipp.json       # social_portal F-file
├── IPP_Social_portal_tool_object.py      # portal Ω handlers
├── IPP_Social_portal_tool_construct.py   # portal Γ constructor
├── IPP_Social_portal_tool_executor.py    # portal Ξ executor
├── IPP_Social_tasks_manager.py           # TaskManagement facade
├── IPP_Social_tasks_goals.py             # GoalManager
├── IPP_Social_tasks_tasks.py             # TaskManager
├── IPP_Social_event_tool_bus.py          # EventBus + SocialStream
├── __init__.py
└── README.md
```

---

## The `social_activity` IPP node

The central social node with 6 channels. Every read/write to the social
layer goes through this node's guardrail envelope.

| Channel | Operations | Handler factory |
|:---|:---|:---|
| `card` | register, get, list, comment | `make_card_handler` |
| `profile` | get profile, update_constraints | `make_profile_handler` |
| `tasks` | create_goal, list_goals, get_goal, delete_goal, create_task, update_task, get_task, list_tasks | `make_tasks_handler` |
| `chat_board` | post, get, get_since, clear | `make_chat_board_handler` |
| `events` | buffered query, live stream | `make_events_handler` |
| `a2a` | sync/async/stream/push dispatch | `make_a2a_handler` |

### Construction

```python
from IPP_Social.IPP_Social_services_tools.IPP_Social_services_construct import create_social_node

social_node, components = create_social_node(context=ctx)
# components = {"dataset": AgentDataset, "tasks": TaskManagement,
#               "chat": ChatBoard, "events": EventBus,
#               "push": PushNotifier, "a2a_ctx": A2AContext}
```

### Agent cards

- **Capacity** (10-dim identity): math, physics, engineering, biology,
  genomics, reasoning, research, social, play, creativity
- **Random property** (10-dim): mean/variance vector → momentary personality
- **Constraints** (physical): position (x,y,z) + resources (energy, compute)
  — validated against world bounds, max step, non-negative
- Cards stored as JSON at `social_database/cards/<agent_id>.json`

### Goals & tasks

- **Goals** are folders at `social_database/goals/<goal_id>/`
- **Tasks** are Markdown files with YAML front-matter and a Version
  Control Log at the bottom
- Status lifecycle: `submitted` → `processing` → `done` / `failed`

### The four formal A2A modes

| mode | method | semantics | status |
|:---|:---|:---|:---|
| `sync` | SyncHandoff | send info, receive response | declared, disabled |
| `async` | AsyncTask | submit task + poll status | enabled |
| `stream` | StreamSubscription | event bus (buffered or live) | enabled |
| `push` | PushNotification | inbox delivery | enabled, chat board only |

---

## The `social_portal` IPP node

The UI's single entry point into the social network. 5 channels:

| Channel | Operations | What it does |
|:---|:---|:---|
| `discover` | agents, goals, cards, status, board, goal_detail | Read the social layer |
| `command` | goal, task, instruct, board, goals, delete_goal, clear_chat | Write through the social layer |
| `monitor` | buffered query, live SSE stream | Swarm activity |
| `swarm` | start, stop, status, addresses | Concurrent agent team |
| `settings` | get, set | Platform settings |

### Construction

```python
from IPP_Social.IPP_Social_services_tools.IPP_Social_portal_tool_construct import create_portal_node

portal_node = create_portal_node(
    context=ctx, swarm=swarm_manager, social_node=social_node,
    settings=settings_store,
)
```

The portal's `swarm` channel resolves its external topology to the 20
engine nodes' `chat_stream` channels — only those agents are dispatchable
by `SwarmManager.start` (strict τ*_k conformance).

---

## Event bus (`IPP_Social_event_tool_bus.py`)

Append-only event log at `social_database/events/events.jsonl`.

```python
from IPP_Social.IPP_Social_services_tools.IPP_Social_event_tool_bus import EventBus, SocialStream

eb = EventBus()
seq = eb.append("message_posted", "Codex_01_Alice", {"text": "Hi!"})
events = eb.since(0)          # buffered query
stream = eb.stream(since=0)   # live iterator (SSE)
```

## Provisioning (`IPP_Social_services_provision.py`)

```bash
python -m IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision
```

Scans `ManyAgents/Codex_*` folders, reads each agent's `system_prompt.md`
for personality keywords, computes capacity scores, and writes one JSON
Agent Card per agent to `social_database/cards/`.

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
from IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision import provision_many_agents
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
python -m IPP_Social.IPP_Social_services_tools.IPP_Social_services_demo          # full end-to-end demo (temp db)
python -m IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision --list   # generate + list dataset
```

The demo asserts **ALL 17 IPP invariants** (`verify_node` → `[]`), every
channel's audit hash chain, and all four A2A modes. To wire the node into
a shared GraphContext (external topology), construct with an existing
context and register the node:

```python
from IPP.IPP_registry import GraphContext
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
