# codex_growth/ — the GROWTH agent (IPP v0.2.8)

Improves node `.md` notes by considering new analysis & information (web
search, file read) and **EXPANDS the network** — adding new edges, updating
and adding new nodes — using the mutation tools in `the database node`.

## Layout (IPP v0.2.8 node)

| Path | Role |
|---|---|
| `engine/__init__.py` | `CodexGrowthEngine` (AgentEngine subclass) + `construct_engine_node()` |
| `engine/IPP.json` | the engine node (𝔉): channels `ground` · `chat` · `chat_stream` + internal **blocking** edge `ground → chat` |
| `engine/IPP_object.py` | the Objects (Ω_k): `make_ground_handler` / `make_chat_handler` / `make_chat_stream_handler` |
| `engine/IPP_executor.py` | the Executors (Ξ_k): `AgentExecutor` (trace/tool-call audit extras) |
| `tools/__init__.py` | `construct_tools_node()` — the tools node (Γ ⊩ `tools/IPP.json`) |
| `tools/IPP.json` | the tools node (𝔉): channels `invoke` · `list` · `describe` over the shared ToolRegistry, restricted to the growth tool set |
| `tools/IPP_object.py` | the Objects (Ω_k): op-dispatch handlers over `tools.impl` |
| `tools/IPP_executor.py` | the Executors (Ξ_k): `ToolExecutor` (tool identity in the audit) |
| `system_prompt.md` | the growth-tailored system prompt |
| `__init__.py` | `create_agent()` — builds engine + tools + llm nodes through Γ, attaches `engine.node` |

## Use

```python
from codex_growth import create_agent

agent = create_agent(graph, encoder, llm=llm)     # llm optional (live-or-mock)
agent.chat("Improve the agent_memory note", node_id="agent_memory")

# IPP node access
agent.node.invoke("ground", {"task": "…", "node_id": "agent_memory"})
#   ↳ internal edge ground → chat (blocking) runs the grounded agent loop
agent.node.executors["chat"].audit_verify()       # hash chain
agent.node.verify() or "ALL 17 OK"
```

Chat: `python ui/gradio_chat.py --agent codex_growth` → http://127.0.0.3:7860
