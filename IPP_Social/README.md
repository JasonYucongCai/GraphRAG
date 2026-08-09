# IPP_Social — the Multi Agent social layer (strict IPP v0.2.8)

One platform, one shared GraphContext 𝒢, 45 IPP nodes: the LLM, the
`social_activity` node (Agent Cards, 3 properties, goals/tasks, chat
board, event bus, four A2A modes), the **`database` node** (the note
store as an IPP component — 6 channels: project, nodes, edges, graph,
supplement, categories), the **`tools` node** (the SHARED runtime as an
IPP component — 7 channels: invoke, list, describe, graph, encoder,
build, check), the 20 ManyAgents Codex agents (each with its own engine
+ tools node), and the `social_portal` node that the web UI talks to.

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

## Two merged tool packages

After the August 2026 restructure, IPP_Social consists of two clean
package families plus shared infrastructure:

```
IPP_Social/
├── IPP_Social_communication_tools/   ← merged a2a + chat_board
├── IPP_Social_services_tools/        ← merged social_activity + portal
│                                       + task_manager + events
├── social_database/                  ← all persistent data
├── integration.py                    ← build_platform()
├── integration_demo.py               ← headless verification
├── settings.py / paths.py / util.py / errors.py
└── README.md
```

Agent identity and the swarm runtime were both moved to `ManyAgents/`:

```
ManyAgents/
├── agent_management/   ← agent cards, capacity, constraints, dataset
├── swarm/              ← AgentRuntime, SwarmManager, SwarmBus,
│                         SocialResponder, per-agent IPP construction
└── Codex_01_Alice/ … Codex_20_Vivian/
```

### `IPP_Social_communication_tools/` — A2A modes + global chat board

| File | Description |
|:---|:---|
| `IPP_Social_a2a_modes.py` | The four formal A2A methods: sync (declared, disabled), async (task-based), stream (event bus), push (inbox delivery). Contains the `A2A_METHODS` registry and `execute_a2a()` dispatcher. |
| `IPP_Social_a2a_push.py` | Push notifications: per-agent inboxes at `social_database/push/<agent>/inbox.jsonl`. Subscribe, unsubscribe, deliver, and read inbox. |
| `IPP_Social_a2a_async_task.py` | Async task submission + status polling in goal folders. |
| `IPP_Social_a2a_stream.py` | Event bus subscription (buffered or live `SocialStream`). |
| `IPP_Social_a2a_sync.py` | Sync handoff — declared for protocol conformance but currently disabled. |
| `IPP_Social_chatboard_tool.py` | The global chat board: `post(author, text, to_agent_id)` with addressing (`"chat_board"` = broadcast to all, `"agents"` = every agent, `"<agent_id>"` = direct message). Posts deliver push notifications to inboxes. |

### `IPP_Social_services_tools/` — social node + portal + tasks + events

| File | Description |
|:---|:---|
| `IPP_Social_services_ipp.json` | F-file for the `social_activity` IPP node (6 channels: card, profile, tasks, chat_board, events, a2a). |
| `IPP_Social_services_ipp_object.py` | Ω handlers: Agent Card lifecycle (register/get/list/comment), agent profile (capacity/constraints), task CRUD, chat board ops (post/get/clear), event streaming, A2A dispatch. |
| `IPP_Social_services_ipp_executor.py` | Ξ executor: stamps social context (op, mode, agent_ids, errors) into hash-chained audit records. |
| `IPP_Social_services_construct.py` | Γ constructor: builds the social node with all channel handlers and external topology resolved in 𝒢. |
| `IPP_Social_services_provision.py` | Scans `ManyAgents/Codex_*` folders, reads `system_prompt.md` for personality keywords, and generates one JSON Agent Card per agent. |
| `IPP_Social_services_demo.py` | Standalone demo of the social component. |
| `IPP_Social_portal_tool_ipp.json` | F-file for the `social_portal` IPP node (5 channels: discover, command, monitor, swarm, settings). |
| `IPP_Social_portal_tool_object.py` | Portal Ω handlers: discover (agents/goals/board/status), command (goal/task/instruct/board), monitor (live events), swarm (start/stop/status), settings (get/set). |
| `IPP_Social_portal_tool_construct.py` | Portal Γ constructor: resolves swarm topology against 𝒢 and attaches the SwarmManager. |
| `IPP_Social_portal_tool_executor.py` | Portal Ξ executor. |
| `IPP_Social_tasks_manager.py` | `TaskManagement` facade: goal + task CRUD. |
| `IPP_Social_tasks_goals.py` | `GoalManager`: create, list, get, archive, delete goal folders inside `social_database/goals/`. |
| `IPP_Social_tasks_tasks.py` | `TaskManager`: create, update, list, get tasks (Markdown files with YAML front-matter and VCL) inside goal folders. |
| `IPP_Social_event_tool_bus.py` | `EventBus`: append-only event log at `social_database/events/events.jsonl`. `SocialStream`: live iterator for SSE streaming. |

## Strict IPP v0.2.8 wiring

- **One 𝒢**: the LLM node, social_activity, the database node, the tools
  node, all 20 agents' engine+tools nodes and the portal node are
  constructed through Γ into a single `GraphContext` (45 registered
  nodes). The per-agent tools nodes' invoke channel resolves its
  downstream edge to the shared tools node's invoke channel.
- **Per-agent identity**: each ManyAgents copy's `engine/IPP.json` +
  `tools/IPP.json` are finalized by `ManyAgents/swarm/agent_ipp.py` with
  its own `node_id` (`Codex_01_Alice_engine` …), its own handler refs
  (`ManyAgents.<agent>.engine.IPP_object:…`), and its own audit log
  endpoints — no two nodes share an identity.
- **Constructor-resolved topology**: the portal's `command`/`discover`
  channels resolve their downstream to `social_activity`'s SocialOp
  channels; the `swarm` channel resolves to the 20 engine nodes'
  `chat_stream` channels (exact logical-type matching) — and
  `SwarmManager.start` refuses agents outside that resolved set
  (Axiom X5 conformance).
- **Everything through guardrail envelopes**: portal → social (goals,
  tasks, board posts), portal → agent engines (`chat_stream` with a
  live `context["on_event"]` pushing each thinking/tool/message step to
  the swarm bus), agents → social (task completion + board broadcast).
  Every channel is audited with hash-chained records (Axiom X3).

## The web portal (ui)

- The **brand title** is a clickable button back to the Control Center.
- The **Multi Agent tab**: left sidebar lists the 20 agents with
  avatars + status dots; name a goal and give instructions to the team
  (select agents via pill toggles, then click **✅ update team** to
  commit the selection); instruct one agent directly; browse goals.
  The main canvas shows **mini agent boxes** — each agent's live
  thinking/tool calls — plus the right panels (Agent Process, Inter
  Agent Chat, Global Chat Board), all fed over SSE from the swarm bus.
- API: `/api/social/agents`, `/api/social/goals`, `/api/social/goal`,
  `/api/social/board`, `/api/social/instruct`,
  `/api/swarm/start|stop|status`, `/api/swarm/events` (SSE).

## Run

```bash
python ui/server.py                     # control center → 127.0.0.3:8000
python -m IPP_Social.integration_demo   # headless strict-IPP verification
python -m IPP_Social.integration_demo --live   # with the real DeepSeek provider
```

---

# Appendix A — Platform Assembly Protocol

## A.1 `build_platform()` — the 7-step assembly

`IPP_Social/integration.py` assembles the complete 45-node platform in
this order (strict constructor precedence):

```
Step 1: GraphContext 𝒢 = GraphContext()
Step 2: LLM node     ← LLMs/IPP.json via Γ (register in 𝒢)
Step 3: social node  ← IPP_Social_services_ipp.json via Γ
        → provision user card (agent_id="user")
        → provision 20 agent cards from ManyAgents/Codex_*
Step 4: database node ← database/IPP.json via Γ (with NoteStore)
Step 5: tools node    ← general_tools/IPP.json via Γ
        → bind_tools(graph, encoder, agents, social_node)
Step 6: 20 agents     ← for each Codex_XX in ManyAgents:
        → finalize agent IPP.json (unique node_id + handler refs)
        → build_engine(agent_id, graph, encoder, provider, ...)
        → construct_agent_nodes(agent_id, engine, ctx)
        → AgentRuntime(agent_id, engine, bus, social_node, ...)
Step 7: portal node   ← IPP_Social_portal_tool_ipp.json via Γ
        → create_portal_node(ctx, swarm, social_node, ...)
        → SwarmManager.attach_topology(portal downstream resolution)
        → bind_tools(social_node=social_node) for router
```

Returns:
```python
{
    "ctx": GraphContext,        # shared 𝒢 with 45 registered nodes
    "llm_node": IPPNode,        # deepseek provider
    "social_node": IPPNode,     # social_activity (6 channels)
    "database_node": IPPNode,   # note store (6 channels)
    "tools_node": IPPNode,      # shared runtime (26 channels)
    "components": {             # social component instances
        "dataset": AgentDataset,
        "tasks": TaskManagement,
        "chat": ChatBoard,
        "events": EventBus,
        "push": PushNotifier,
        "a2a_ctx": A2AContext,
    },
    "portal_node": IPPNode,     # social_portal (5 channels)
    "swarm": SwarmManager,      # owns 20 AgentRuntimes
    "runtimes": {               # agent_id → AgentRuntime
        "Codex_01_Alice": AgentRuntime, ...
    },
    "settings": SettingsStore,  # persisted settings
}
```

## A.2 UI → portal → social_activity flow

Every Multi Agent UI operation goes through this exact chain:

```
UI (multiagent.js)
  │  HTTP POST/GET
  ▼
ui/server.py  →  _portal_invoke(channel, payload)
  │  strips None values for O1 conformance
  ▼
portal_node.invoke(channel, clean_payload)
  │  guardrail envelope: ι_pre → π → Ω → ι_post → ρ → τ*
  ▼
portal Ω handler (portal/IPP_object.py)
  │  discover  → social_node.invoke("card"/"tasks"/"chat_board", ...)
  │  command   → social_node.invoke("tasks"/"chat_board", ...)
  │  swarm     → SwarmManager.start/stop/status
  ▼
social_node.invoke(channel, payload)
  │  guardrail envelope
  ▼
social Ω handler (social_activity/IPP_object.py)
  │  card    → dataset.load/save_card
  │  tasks   → TaskManagement.create/get/update
  │  chat    → ChatBoard.post/get/clear
  │  events  → EventBus.since/stream
  │  a2a     → execute_a2a() dispatcher
```

## A.3 Chat Board Message Lifecycle

```
1. Alice posts social_post(text="Hi", to_agent_id="agents")
2. tools_node.invoke("invoke", {tool: "social_post", args: {...}, agent_id: "Codex_01_Alice"})
3. impl_execute_tool routes to ("social_activity", "chat_board", "post")
4. _social_post adapter: {op: "post", author: "Codex_01_Alice", text: "Hi", to: "agents"}
5. social_node.invoke("chat_board", payload)
6. chat_board Ω handler calls ChatBoard.post("Codex_01_Alice", "Hi", to_agent_id="agents")
7. ChatBoard.post:
   a. Validate author exists (load_card) → skip for "user"/"portal"
   b. Create Message(message_id=auto-increment, author, text, to_agent_id, ts=now)
   c. Append to board.jsonl (thread-safe with RLock)
   d. Emit "message_posted" event to EventBus
   e. Fan-out: for each target agent, PushNotifier.deliver() to inbox
      - to="agents" → all 19 other agents, kind="broadcast"
      - to="Codex_08_Julia" → that agent, kind="direct_message"
      - to="" / "chat_board" → all agents, kind="board_broadcast"
   f. Fan-out: deliver to all push subscribers, kind="chat_board_push"
   g. Return {message: Message.to_dict(), push_delivered_to: [...]}
8. Result flows back: _serialize_social_result extracts "content" = "ok" → now serialized text
9. LLM receives tool_result with the formatted board content
```

## A.4 Per-Agent IPP Finalization

`ManyAgents/swarm/agent_ipp.py` finalizes each agent's IPP.json:

```
Input:  ManyAgents/Codex_04_Fiona/engine/IPP.json
        node_id = "codex_normal_engine"  ← shared template
        handler = "codex_normal.engine.IPP_object:make_ground_handler"

Output: Same file, rewritten:
        node_id = "Codex_04_Fiona_engine"
        handler = "ManyAgents.Codex_04_Fiona.engine.IPP_object:make_ground_handler"
        chat_stream handler = "ManyAgents.swarm.IPP_object:make_live_chat_stream_handler"
        log_endpoint = "graph_data/logs/IPP/Codex_04_Fiona_engine.chat_stream.jsonl"

Same process for tools/IPP.json:
        node_id = "Codex_04_Fiona_tools"
        handler = "ManyAgents.Codex_04_Fiona.tools.IPP_object:make_invoke_handler"
```

The `make_live_chat_stream_handler` replaces the default chat_stream
handler — it pushes every thinking/tool/message step onto the SwarmBus
via `context["on_event"]`, enabling the UI's live trace. The construction
is **idempotent**: if the file already carries the correct node_id,
`finalize_agent_ipp` skips it.

## A.5 SwarmBus Event Types

Events flowing through the in-memory SwarmBus (fed to UI via SSE):

| Event type | agent_id | Payload |
|:---|:---|:---|
| `agent_started` | Codex_XX | `{task_id, goal_id, text}` |
| `agent_event` | Codex_XX | `{event: {type, tool?, args?, content?, error?}, task_id}` |
| `agent_done` | Codex_XX | `{task_id, answer, tokens}` — from `_complete_socially` |
| `agent_error` | Codex_XX | `{task_id, error}` — from `_process` exception handler |
| `agent_instructed` | Codex_XX | `{goal_id, text}` — from `instruct()` |
| `agent_reply_enqueued` | Codex_XX | `{reply_to, message_id}` — from SocialResponder |
| `swarm_started` | portal | `{goal_id, goal_title, agents: [...]}` |
| `swarm_stopped` | portal | `{}` |
| `swarm_skipped` | Codex_XX | `{reason}` — agent outside resolved topology |

## A.6 AgentRuntime Worker Loop

```
AgentRuntime._run_loop():
  while not self._stop:
    task = self._queue.get()           # block until task arrives
    if task is None: break              # sentinel from stop()
    try:
      self._process(task)
    except Exception:
      self._set_status("error", str(exc)[:120])
      self.bus.emit("agent_error", self.agent_id, {task_id, error})

AgentRuntime._process(task):
  self.current_task = task
  self._set_status("running", ...)
  self.bus.emit("agent_started", ...)
  try:
    if self.concurrency is not None:
      self.concurrency.acquire()        # wait for semaphore slot
    try:
      engine.llm_stream = bool(settings.get("llm_streaming", False))
      guarded = engine.node.invoke(
        "chat_stream",
        {"task": task_text, "node_id": task_node_id},
        context={"on_event": self._on_event}   # ← live push to SwarmBus
      )
    finally:
      if self.concurrency is not None:
        self.concurrency.release()
    out = guarded.payload or {}
    answer = out.get("answer", "")
    self.runs_completed += 1
    self._set_status("done", ...)
    self._complete_socially(task, answer, tokens, error=None)
  except Exception:
    self._set_status("error", ...)
    self._complete_socially(task, "", 0, error=str(exc))

AgentRuntime._complete_socially():
  # Report back to the social layer:
  social_node.invoke("tasks", {op: "update_task", goal_id, task_id,
                               status: "done"/"failed", note: "answer: ..."})
  # Post to chat board for team visibility:
  social_node.invoke("chat_board", {op: "post",
                                    author_agent_id: agent_id,
                                    text: answer_or_error,
                                    to_agent_id: "agents",
                                    tags: ["swarm", "done"/"failed"]})
```

## A.7 SwarmManager.start() Protocol

```
SwarmManager.start(goal_title, instructions, agent_ids, goal_id):
  1. Filter agent_ids to known runtimes
  2. Create or reuse goal folder via social_node.invoke("tasks", ...)
     - If goal_id given: get_goal, reuse
     - Else: create_goal
  3. For each selected agent:
     a. Check topology: (engine_node.node_id, "chat_stream") in _topology
        → skip if not (τ*_k enforcement)
     b. Stuck-task recovery: clear stale processing tasks for idle workers
     c. Create task via social_node.invoke("tasks", {op: "create_task"})
        → assigns to this agent, status="processing"
     d. rt.enqueue({task_id, goal_id, text: instructions})
     e. rt.start()  → ensures worker thread is alive
  4. Emit "swarm_started" to SwarmBus
  5. Auto-start SocialResponder (conversation loop)
  6. Return {ok: True, goal_id, agents: started, status: swarm.status()}
```
