# codex_RAG/ — the RETRIEVAL / RAG agent (IPP v0.2.8)

Operates on and **UNDERSTANDS the network**, then outputs information: it
materializes local graphs, vector-searches the encoder layer, reads nodes and
summarizes local graphs to answer queries — grounded in the graph
(**read-only**; no database mutations).

## Layout (IPP v0.2.8 node)

| Path | Role |
|---|---|
| `engine/__init__.py` | `CodexRAGEngine` (AgentEngine subclass) + `construct_engine_node()` |
| `engine/ipp.json` | the engine node (𝔉): channels `ground` · `chat` · `chat_stream` + internal **blocking** edge `ground → chat` |
| `engine/IPP_object.py` | the Objects (Ω_k): `make_ground_handler` / `make_chat_handler` / `make_chat_stream_handler` |
| `engine/IPP_executor.py` | the Executors (Ξ_k): `AgentExecutor` (trace/tool-call audit extras) |
| `tools/__init__.py` | `construct_tools_node()` — the tools node (Γ ⊩ `tools/ipp.json`) |
| `tools/ipp.json` | the tools node (𝔉): channels `invoke` · `list` · `describe`, restricted to the retrieval-only RAG tool set |
| `tools/IPP_object.py` | the Objects (Ω_k): four-phase lifecycle invocation via `tools.IPP.ToolRegistry` |
| `tools/IPP_executor.py` | the Executors (Ξ_k): `ToolExecutor` (tool identity in the audit) |
| `system_prompt.md` | the RAG-tailored system prompt |
| `__init__.py` | `create_agent()` — builds engine + tools + llm nodes through Γ, attaches `engine.node` |

## Use

```python
from codex_RAG import create_agent

agent = create_agent(graph, encoder, llm=llm)
agent.chat("What concrete manifolds live at total 66?", node_id="total_66")

# IPP node access
agent.node.invoke("ground", {"task": "…", "node_id": "total_66"})
#   ↳ internal edge ground → chat (blocking) runs the grounded retrieval loop
agent.node.executors["chat"].audit_verify()       # hash chain
agent.node.verify() or "ALL 17 OK"
```

Chat: `python ui/gradio_chat.py --agent codex_RAG` → http://127.0.0.3:7860
