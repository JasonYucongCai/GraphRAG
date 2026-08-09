# recursive_agents — the self-adaptive recursive agent chain (Section A)

The **bootstrap-compiler analogy** (Rust / C / C++): we do not have a
self-improving agent yet, so this small deterministic compiler (Γ)
compiles the **first recursive agent — `agent_a1`** — strictly per
**IPP v0.2.8** (the first recursive structure we know works) and
completes **the first compilation**. Then `agent_a1` **thinks, evaluates
and self-acts** — through **its own tools node** — to create `agent_a2`,
test it with feedback and keep improving it; and `agent_a2` has the
**same ability**: it creates `agent_a3`.

## The agent-construction tool suite (in every agent's tools node)

Each recursive agent's tools node carries the hands with which it
generates the next agent (each tool = an IPP channel through the
guardrail envelope, hash-chained audited):

| Tool | Capability |
|:---|:---|
| `agent_plan` | THINK — the deterministic construction plan |
| `agent_generate` | GENERATE — render the templates → the next agent's folders |
| `agent_create` | CREATE — compile + construct (Γ, 7-step protocol) + verify ALL 17 invariants |
| `agent_evaluate` | EVALUATE — 17 invariants + audit chains + channel surface |
| `agent_test` | TEST — ground→chat pipeline through the envelopes + latency probe → feedback |
| `agent_improve` | IMPROVE — test → deterministic patch → reconstruct → retest (feedback logged) |
| `agent_deploy` | DEPLOY — generate + construct + register in the chain |
| `agent_status` | report the constructed chain |

Plus `invoke` / `list` / `describe` over the **shared tools node**
(`general_tools`) for the general capability surface (read_file,
web_search, get_local_graph, …) — one execution plane, one audit trail.
The LLM sees the whole surface (24 tools); with a live provider the
agent drives the suite itself via chat; offline, the bootstrap executes
the same plan through the agent's tools.

## Layout — every agent is comprehensive and self-contained

```
recursive_agents/
├── runtime/                      ← the shared machinery
│   ├── compiler.py               ← AgentCompiler (Γ): plan / compile / construct /
│   │                                verify / test / improve / deploy
│   ├── engine.py                 ← RecursiveAgentEngine (the agentic loop)
│   └── templates/                ← the SOURCE (F-files, Ω/Ξ modules, READMEs,
│                                    system prompt) — rendered per agent
├── agent_a1/                     ← ⭐ OUTPUT of the first compilation
│   ├── README.md  system_prompt.md  __init__.py
│   ├── agent_a1_engine/          ← IPP.json · IPP_object.py · IPP_executor.py
│   │                                · README.md · __init__.py   (ground/chat/chat_stream)
│   └── agent_a1_tools/           ← IPP.json · IPP_object.py · IPP_executor.py
│                                    · README.md · __init__.py   (11 channels)
├── agent_a2/                     ← created BY agent_a1 via its tools node
├── agent_a3/                     ← created BY agent_a2 (the ability recurs)
├── feedback/                     ← improvement feedback logs (agent_a2.txt …)
└── bootstrap.py                  ← headless chain verification
```

Every generated agent mirrors the proven codex structure: each engine /
tools folder carries its **own F-file, Ω handler module, Ξ executor
module and README**, plus the agent-level README + system prompt — no
copy-pasted stubs; every piece is real, importable code rendered from
the templates.

## Run it

```bash
python -m recursive_agents.bootstrap          # offline (MockProvider)
python -m recursive_agents.bootstrap --live   # real DeepSeek (drives the chat)
```

```
=== 0. FIRST COMPILATION — the bootstrap compiler builds a1 ===   ALL 17 OK
=== 1. INSTRUCT agent_a1 → create agent_a2 (via a1's TOOLS) ===
     THINK → GENERATE → CREATE → EVALUATE → TEST → IMPROVE → DEPLOY   ✓
=== 2. INSTRUCT agent_a2 → create agent_a3 (the ability recurs) ===  ✓
=== 3. the chain — every agent verified + documented ===              ✓
```

## How it is strictly IPP v0.2.8

- Every agent = **2 IPP nodes** (engine + tools), each declared by its
  own `IPP.json` and constructed through the **7-step Γ protocol**:
  ports, handlers (Ω factories bound from GraphContext.bindings),
  guardrails, constructor-resolved topology, internal edge `ground →
  chat` (I15/I16/I17).
- Every call flows through the guardrail envelope
  ι_pre → π → Ω → ι_post → ρ → τ* with hash-chained audit records
  (I2/I6); the audit extras record the construction reports.
- **ALL 17 invariants verified** on every constructed node
  (`agent_evaluate`).
- The agent-construction channels `agent_create` / `agent_generate` /
  `agent_evaluate` / `agent_test` / `agent_improve` / `agent_deploy`
  are the **recursion surface**: they invoke the shared compiler (the
  chain's Γ) — the same way a self-improving agent would, deterministic
  for now.
- Tools nodes enforce their ACL and delegate execution + definitions to
  the shared tools node (`general_tools`).
- Log endpoints: `recursive_agents/graph_data/logs/IPP/<node>.<channel>.jsonl`.

## The improvement loop (feedback)

`agent_improve` runs **test → feedback → deterministic patch →
reconstruct → retest**. The template deliberately ships the chat channel
with a tight `max_latency_ms: 30000`; the test flags it, the patch bumps
it to `600000`, the retest passes — visible in `feedback/agent_a2.txt`.
This is the prototype of the self-improvement cycle that Section B's
adaptive constructor will build on.
