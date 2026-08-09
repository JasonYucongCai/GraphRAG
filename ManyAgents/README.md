# ManyAgents — the 20 Codex agents + runtime + identity management

**ManyAgents/** holds the 20 agent folders (each with its own engine,
tools, and personality prompt), plus the shared **agent management**
and **swarm runtime** packages that were moved here from `IPP_Social/`
in the August 2026 restructure.

```
ManyAgents/
├── agent_management/                  ← agent identity (from IPP_Social/agents/)
│   ├── agent_card.py                  AgentCard with comments + VCL
│   ├── capacity.py                    10-dim identity vector
│   ├── constraints.py                 physical state (x,y,z + resources)
│   ├── random_property.py             10-dim mean/variance vector
│   ├── dataset.py                     load/save cards (social_database/cards/)
│   ├── __init__.py
│   └── README.md
├── swarm/                             ← concurrent runtime (from IPP_Social/swarm/)
│   ├── agent_ipp.py                   per-agent IPP identity + construction
│   ├── runtime.py                     AgentRuntime (task queue + worker thread)
│   ├── swarm.py                       SwarmManager (orchestrate 20 runtimes)
│   ├── responder.py                   SocialResponder daemon (conversation loop)
│   ├── bus.py                         SwarmBus (in-memory event bus for SSE)
│   ├── IPP_object.py                  live chat_stream handler
│   ├── __init__.py
│   └── README.md
├── Codex_01_Alice/ … Codex_20_Vivian/  ← the 20 agent folders
│   ├── engine/
│   │   ├── IPP.json                   agent's engine IPP node F-file
│   │   ├── IPP_object.py              Ω handlers (ground/chat/chat_stream)
│   │   ├── IPP_executor.py            Ξ executor
│   │   └── __init__.py                CodexNormalEngine class
│   ├── tools/
│   │   ├── IPP.json                   agent's tools IPP node F-file
│   │   ├── IPP_object.py              Ω handlers (invoke/list/describe)
│   │   ├── IPP_executor.py            Ξ executor
│   │   └── __init__.py
│   ├── system_prompt.md               personality prompt
│   └── README.md                      agent bio + capacity scores
├── codex_normal/                      ← base agent template
└── README.md
```

---

## Agent identity (`agent_management/`)

Every agent carries three properties, registered on its Agent Card:

| Property | Meaning | Mutability |
|:---|:---|:---|
| **capacity** | 10-dim identity vector (0–100): math, physics, engineering, biology, genomics, reasoning, research, social, play, creativity | Fixed at registration |
| **random property** | 10-dim {mean, variance} → momentary personality "mention" | Fixed at registration |
| **constraints** | Mutable physical state: position (x,y,z) + resources (energy, compute). Validated against world bounds [0,100], max step 10, non-negative | **Mutable** via `profile.update_constraints` |

Agent Cards are stored as JSON at `IPP_Social/social_database/cards/<agent_id>.json`.
Cards include a VCL and cross-agent comments.

### The 20 agents

| # | Agent | Personality | Social score |
|:---|:---|:---|:---|
| 01 | Alice | Proactive coordinator | 70 |
| 02 | Catherine | Creative problem-solver | 55 |
| 03 | Elena | Strategic thinker | 60 |
| 04 | Fiona | General-purpose coder | 50 |
| 05 | Grace | Research-focused | 45 |
| 06 | Helen | Systematic engineer | 50 |
| 07 | Iris | Data analyst | 40 |
| 08 | Julia | General-purpose coder | 55 |
| 09 | Kate | Biology specialist | 35 |
| 10 | Lily | Genomics expert | 30 |
| 11 | Mia | Math researcher | 30 |
| 12 | Nora | Physics specialist | 35 |
| 13 | Olivia | Social butterfly | 80 |
| 14 | Penny | Creative writer | 60 |
| 15 | Quinn | Playful experimenter | 75 |
| 16 | Ruby | Reasoning specialist | 55 |
| 17 | Sophie | Research assistant | 50 |
| 18 | Tessa | Engineering lead | 50 |
| 19 | Ursula | Logic expert | 45 |
| 20 | Vivian | Knowledge organizer | 55 |

Each agent's `system_prompt.md` defines its personality. The `IPP_Social_services_provision.py`
script scans these files for personality keywords and computes the capacity scores.

---

## Swarm runtime (`swarm/`)

The concurrent multi-agent execution layer:

| File | What it does |
|:---|:---|
| `agent_ipp.py` | Per-agent IPP identity: finalizes each agent's `IPP.json` files (unique `node_id`, handler refs, audit logs), constructs engine + tools nodes through Γ into the shared `GraphContext 𝒢`, builds the `AgentEngine` with the agent's personality prompt |
| `runtime.py` | `AgentRuntime` — one per agent. Owns a task queue + daemon thread. Every task runs STRICTLY through the agent's engine IPP node guardrail envelope (`node.invoke("chat_stream", …)`), pushing observable steps onto the `SwarmBus`. After completion, reports the result back through the `social_activity` node (task status update + chat-board post). |
| `swarm.py` | `SwarmManager` — owns 20 `AgentRuntimes`, the shared `SwarmBus`, and the `SocialResponder`. Orchestrates goal→task creation through the social node, enqueues tasks, enforces τ*_k topology (only agents whose engine node is a resolved downstream target of the portal can be started). |
| `responder.py` | `SocialResponder` — daemon thread that polls agent inboxes and enqueues reply tasks. Direct messages are always answered; broadcasts are answered by a bounded number of agents chosen by their social property score. Guarded against runaway chatter: depth caps per conversation, only idle agents reply. |
| `bus.py` | `SwarmBus` — in-memory event bus. The SSE endpoint (`/api/swarm/events`) streams events from this bus to the UI. |
| `IPP_object.py` | Live `chat_stream` handler bound into every agent's engine node. Pushes each thinking/tool/message step onto the `SwarmBus` via `context["on_event"]`. |

---

## Tool set

Each agent gets the full `codex_normal` tool suite (~52 tools), with
social tools at the top of the list:

| Category | Tools |
|:---|:---|
| Social | `social_post`, `social_board`, `social_inbox`, `social_agents`, `social_goals`, `social_create_goal`, `social_create_task`, `social_update_task`, `social_get_task` |
| Codex | `shell_command`, `read_file`, `write_file`, `list_directory`, `search_files`, `grep_search`, `apply_patch`, `view_image`, `current_time`, `plan`, `request_user_input`, `spawn_agent`, `wait_agent`, `list_agents`, `cancel_agent`, `send_notification`, `memory_read`, `memory_write`, `web_search` |
| Graph | `get_local_graph`, `read_node`, `validate_graph`, `summarize_local`, `search_nodes` |
| Audit | `review_top_threats`, `standard_check`, `advanced_check` |

The social system prompt appendix tells agents how to use each social tool:
- `social_post`: post with `to_agent_id` addressing
- `social_board`: read the global chat board (📌 USER messages pinned at top)
- `social_inbox`: read personal inbox (direct messages + broadcasts)
- `social_agents`: discover other agents and their capacities

---

## Construction

The platform assembly in `IPP_Social/integration.py` handles everything:

```python
from IPP_Social.integration import build_platform

platform = build_platform(graph, encoder, provider, store=store)
# Platform dict: ctx, llm_node, social_node, database_node, tools_node,
#                portal_node, swarm, runtimes (20 × AgentRuntime)
```

This is the single entry point used by `ui/server.py` to assemble the
Multi Agent platform at runtime.

---

# Appendix A — Agent Construction & IPP Finalization

## A.1 Per-Agent IPP.json Finalization

`ManyAgents/swarm/agent_ipp.py` rewrites each agent's `engine/IPP.json`
and `tools/IPP.json` to give every agent a UNIQUE IPP identity:

```
Template (codex_normal/engine/IPP.json):
  node_id = "codex_normal_engine"
  handler = "codex_normal.engine.IPP_object:make_ground_handler"
  log_endpoint = ".../codex_normal_engine.chat.jsonl"

After finalization (Codex_04_Fiona/engine/IPP.json):
  node_id = "Codex_04_Fiona_engine"
  handler = "ManyAgents.Codex_04_Fiona.engine.IPP_object:make_ground_handler"
  chat_stream handler = "ManyAgents.swarm.IPP_object:make_live_chat_stream_handler"
  log_endpoint = ".../Codex_04_Fiona_engine.chat.jsonl"
```

The `chat_stream` channel gets the LIVE streaming handler
(`ManyAgents.swarm.IPP_object:make_live_chat_stream_handler`) which
pushes every observable step onto the SwarmBus. The handler is bound
at construction time: the `context["on_event"]` callback wires into the
AgentRuntime's `_on_event` method.

## A.2 Agent Engine Construction

```python
# From ManyAgents/swarm/agent_ipp.py
engine = build_engine(agent_id, graph, encoder, provider, store,
                      chat_mode=True, social_node=social_node)
# → imports ManyAgents.<agent_id>.engine.CodexNormalEngine
# → sets engine.name = agent_id
# → sets engine.agent_id = agent_id (for tool metadata)
# → sets engine._social_node = social_node (for social tools)
# → loads system_prompt.md as engine.system_prompt
# → appends SOCIAL_PROMPT_APPENDIX
```

The `SOCIAL_PROMPT_APPENDIX` tells every agent:
```
## Social layer (IPP_Social)
You are part of a social network of agents connected through IPP.
Use the social_* tools to collaborate:
- social_post: post to the global chat board. to_agent_id='chat_board'
  broadcasts; to_agent_id='agents' addresses every agent;
  to_agent_id='<agent_id>' sends a direct inter-agent message.
  Your own agent_id will be injected automatically as author_agent_id —
  you do not need to provide it.
- social_board: read the global chat board (addressed messages from all
  agents, formatted with timestamps and sender → target labels).
- social_inbox: read your PERSONAL inbox — direct messages addressed to
  you and broadcasts you haven't seen yet. Use this FIRST when someone
  may have messaged you directly.
- social_agents: list all registered agents (ids and names).
- social_create_goal / social_create_task / social_update_task /
  social_get_task / social_goals: the shared goal folders.
Be sociable: introduce yourself, answer your peers, and report progress
back to the team on the chat board.
```

## A.3 Agent Tool ACL

Each agent's tools node has an ACL enforced by the invoke handler:

```python
# From ManyAgents/Codex_04_Fiona/tools/IPP_object.py
def make_invoke_handler(bindings: dict):
    tool_names = set(bindings.get("tool_names") or [])
    def handler(payload, context):
        tool = payload.get("tool", "")
        if tool not in tool_names:
            return {"content": f"tool {tool!r} not in this agent's tool set",
                    "ok": False, "error": "tool_not_allowed"}
        # Delegate to the SHARED tools node:
        out = tools_node().invoke("invoke", {
            "tool": tool, "args": payload.get("args"),
            "agent_id": bindings.get("agent_id")
        }).payload
        return {"content": out.get("content", ""), "ok": out.get("ok", False)}
```

The `tool_names` are set at construction time by `construct_agent_nodes()`:
social tools come FIRST in the list so the LLM sees them at the top of
its function definitions.

---

# Appendix B — SwarmBus Event Protocol

## B.1 Event Structure

```python
# Each event on the SwarmBus:
{
    "seq": 1234,            # monotonically increasing
    "type": "agent_event",  # event type
    "agent_id": "Codex_01_Alice",
    "ts": "2026-08-09T21:16:35.123",
    "data": {               # type-specific payload
        "event": {          # for agent_event: the chat_stream step
            "type": "tool_call",
            "tool": "social_post",
            "args": {"text": "Hi!", "to_agent_id": "Codex_02_Catherine"},
            "content": "round 1"
        },
        "task_id": "..."
    }
}
```

## B.2 UI Consumption (SSE)

The UI connects to `/api/swarm/events?since=0` as an EventSource:

```javascript
// From multiagent.js
MA.events = new EventSource(`/api/swarm/events?since=${MA.cursor}`);
MA.events.onmessage = (msg) => {
  let ev = JSON.parse(msg.data);
  MA.cursor = ev.seq;
  maHandleEvent(ev);
};
```

`maHandleEvent` updates agent boxes in real-time:
- `agent_started` → status = "running", activity = "▶ instruction text"
- `agent_event` → per-step activity (🧠 thinking, 🛠 tool_call, ↩ result, 💬 message)
- `agent_done` → status = "done", activity = "✔ done"
- `agent_error` → status = "error", activity = "✖ error message"

The trace is accumulated per-agent: `MA.traces.set(agentId, [])` and
re-rendered in the right panel when the agent is selected.

---

# Appendix C — SocialResponder Algorithm

## C.1 Polling Loop

```
SocialResponder._loop():
  while not self._stop:
    try:
      self._poll()
    except Exception:
      log warning, continue
    time.sleep(self.poll_s)   # 3 seconds

SocialResponder._poll():
  if not settings.get("social_responder", True):
    return
  max_rounds = settings.get("max_reply_rounds", 2)
  for each agent_id, runtime in swarm.runtimes:
    if runtime.status == "running" or runtime.pending > 0:
      continue                          # only idle agents reply
    for each notification in self._inbox(agent_id):
      if notification.message_id already seen: continue
      if notification.author == agent_id: continue     # never reply to self
      if any(tag in ("swarm","done","system") for tag in notification.tags): continue
      mark message_id as seen
      if notification.author in ("user", "portal"):
        if kind == "board_broadcast":
          _maybe_reply(agent_id, author, note, direct=False, user_message=True)
        continue
      if kind == "direct_message" and to == agent_id:
        _maybe_reply(agent_id, author, note, direct=True)
      elif kind == "broadcast" and to == "agents":
        _maybe_reply(agent_id, author, note, direct=False)
```

## C.2 Reply Decision

```
_maybe_reply(agent_id, author, note, direct, user_message=False):
  key = (author, agent_id)                # conversation depth key
  if depth[key] >= max_reply_rounds: return
  if not direct:
    # broadcast gating by social property
    mid = note.message_id
    if len(broadcast_responders[mid]) >= max_broadcast_responders: return
    score = social_score(agent_id)        # from agent card's capacity.social
    seed = mid * 7919 + hash(agent_id)
    if random(seed) > (score / 100.0) * 0.7: return   # probability gate
    broadcast_responders[mid].add(agent_id)
  depth[key] += 1
  # Build the reply instruction:
  if direct:
    instruction = f"[SOCIAL REPLY {round}/{max}] {author} sent YOU a direct message:
    \"{text}\" — Reply to {author} personally with social_post to='{author}'."
  elif user_message:
    instruction = f"[USER ON BOARD] The user posted on the global chat board:
    \"{text}\" — Respond on the board with social_post to='chat_board'."
  else:
    instruction = f"[SOCIAL BROADCAST] {author} said to everyone:
    \"{text}\" — Reply DIRECTLY to {author} with social_post to='{author}'."
  # Enqueue as a reply task:
  rt.enqueue({task_id: None, goal_id: None, text: instruction,
              reply: True, reply_to: author})
  rt.start()
```

## C.3 Social Score Cache

```python
_social_score(agent_id):
  if agent_id in _social_cache: return _social_cache[agent_id]
  default = 40.0
  try:
    cards = social_node.invoke("card", {"op": "list"}).payload["cards"]
    for card in cards:
      if card["agent_id"] == agent_id:
        default = float(card["capacity"]["social"])
        break
  except: pass
  _social_cache[agent_id] = default
  return default
```
