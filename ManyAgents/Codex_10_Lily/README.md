# codex_normal/ — the general-purpose codex agent (IPP v0.2.8)

The usual codex agent that can **DO things**: read/write files, run shell
commands, search code, plan, spawn sub-agents, memory, notifications and web
search. This is the agent you chat with for general tasks.

## Layout (IPP v0.2.8 node)

| Path | Role |
|---|---|
| `engine/__init__.py` | `CodexNormalEngine` (AgentEngine subclass) + `construct_engine_node()` |
| `engine/IPP.json` | the engine node (𝔉): channels `ground` · `chat` · `chat_stream` + internal **blocking** edge `ground → chat` |
| `engine/IPP_object.py` | the Objects (Ω_k): `make_ground_handler` (inline depth-3 grounding — the base `AgentEngine` has no `_ground`) / `make_chat_handler` / `make_chat_stream_handler` |
| `engine/IPP_executor.py` | the Executors (Ξ_k): `AgentExecutor` (trace/tool-call audit extras) |
| `tools/__init__.py` | `construct_tools_node()` — the tools node (Γ ⊩ `tools/IPP.json`) |
| `tools/IPP.json` | the tools node (𝔉): channels `invoke` · `list` · `describe`, restricted to the full 19-tool general set |
| `tools/IPP_object.py` | the Objects (Ω_k): four-phase lifecycle invocation via `tools.IPP.ToolRegistry` |
| `tools/IPP_executor.py` | the Executors (Ξ_k): `ToolExecutor` (tool identity in the audit) |
| `system_prompt.md` | the general-purpose system prompt |
| `__init__.py` | `create_agent()` — builds engine + tools + llm nodes through Γ, attaches `engine.node` |

> The former `codex_normal/chat.py` was removed (2026-08-07) — it was a
> redundant wrapper around `ui/gradio_chat.py`. Launch all agents uniformly:
> `python ui/gradio_chat.py [--agent codex_growth|codex_RAG|codex_normal]`.

## Use

```python
from codex_normal import create_agent

agent = create_agent(graph, encoder, llm=llm)
agent.chat("Review this repository for exposed secrets")   # full tool suite

# IPP node access
agent.node.invoke("ground", {"task": "…", "node_id": "grag_framework"})
#   ↳ internal edge ground → chat (blocking) runs the grounded general loop
agent.node.executors["chat"].audit_verify()       # hash chain
agent.node.verify() or "ALL 17 OK"
```

Chat: `python ui/gradio_chat.py --agent codex_normal` → http://127.0.0.3:7860
