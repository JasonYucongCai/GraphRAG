# agent_a3_engine — Level 3 Recursive Agent Engine

## Situation

| | |
|:---|:---|
| **Agent** | `agent_a3` (level 3) |
| **Engine location** | `recursive_agents/agent_a3/agent_a3_engine/` |
| **Built by** | The recursive compiler from engine template |
| **IPP version** | v0.2.8 |
| **Architecture** | Copilot-level (not weaker than `assets/copilot_agent_engine`) |

## Components

### `engine.py` — AgentA1Engine
The full agentic loop extending `RecursiveAgentEngine` with:
- **Multi-mode operation**: ask / edit / agent / plan
- **Tool-calling loop**: up to 15 rounds with the full tool surface
- **Streaming events**: `ToolCallEvent` yielding each step
- **Turn tracking**: per-turn context with token accounting
- **Tool execution**: routes through the tools node (guardrail envelope)

### `hooks.py` — HookSystem
Lifecycle hooks at 8 key points:
- `session_start` — first turn of a session
- `user_prompt_submit` — before the LLM call
- `stop` — loop about to exit
- `tool_pre_invoke` / `tool_post_invoke` — around each tool call
- `subagent_start` / `subagent_stop` — sub-agent lifecycle
- `compaction` — context compaction event
- `agent_construct` — when constructing the next agent

### `prompt_assembler.py` — PromptAssembler
Composable system prompt assembly from sections:
- Core identity
- Tool surface (categories + definitions)
- Operating rules
- Construction verification checklist
- IPP constraints
- Working memory + encoder evidence + chain state

### `autopilot.py` — AutopilotController
Detects when agent construction tasks are complete by monitoring:
- Construction sequence completeness (all 8 steps)
- Invariant verification results
- Answer quality signals (PASS/OK/complete)
- Round/timeout thresholds

### `summarizer.py` — ContextSummarizer
Intelligent context compaction when conversation exceeds thresholds:
- Preserves recent messages verbatim
- Summarizes older messages
- Extracts key decisions and errors
- Configurable thresholds (100K chars trigger, 500K max)

## Channels (IPP)

| Channel | Type | Description |
|:---|:---|:---|
| `ground` | deterministic | Materialize local graph + encoder evidence |
| `chat` | agent loop | Full LLM function-calling loop over the tool surface |
| `chat_stream` | observable loop | Streaming events — each step yielded |

**Internal topology:** one blocking internal edge `ground → chat`.

**The engine is the loop; the tools are the hands.** The agent-construction
capability (`agent_create`, `agent_generate`, `agent_evaluate`,
`agent_test`, `agent_improve`, `agent_deploy`, `agent_plan`,
`agent_status`) lives in the agent's tools node
(`recursive_agents/agent_a3/agent_a3_tools`).

## IPP Files

- `IPP.json` — the F-file (node_id `agent_a3_engine`), ports, guardrails
- `IPP_object.py` — the Ω handler factories (bound by Γ)
- `IPP_executor.py` — the Ξ class (audit extras: trace steps, tool calls)

## Guarantees

1. Every call flows through the guardrail envelope: ι_pre → π → Ω → ι_post → ρ → τ*
2. Hash-chained audit on every channel
3. ALL 17 IPP invariants verified at construction
4. The engine is NOT weaker than the reference `assets/copilot_agent_engine`

Constructed by Γ (the recursive compiler) with the 7-step protocol:
objects → guards → external topology → internal wiring → return.
