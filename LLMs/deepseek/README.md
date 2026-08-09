# LLMs/deepseek/ — DeepSeek Provider Scripts

Everything the agents use to talk to DeepSeek's OpenAI-compatible Chat
Completions API lives in this subfolder.

## Files

| File | Role |
|---|---|
| `provider.py` | `LLMResult` (ChatCompletion-like envelope), `DeepSeekProvider` (live, IPP), `MockProvider` (offline, deterministic) |
| `__init__.py` | re-exports `LLMResult`, `DeepSeekProvider`, `MockProvider` |

## The LLM IPP node (v0.2.8)

The `LLMs/` package is also an **IPP v0.2.8 node** declared in `LLMs/IPP.json`
with three channels — `chat` · `complete` · `chat_stream` — each an
independent (Ω, Ξ) pair:

| File | Role |
|---|---|
| `IPP.json` | the IPP Json File (𝔉): ports, process descriptions, executor guardrails, edge capabilities |
| `IPP.py` | `llm_node()` — Γ ⊩ `LLMs/IPP.json` × 𝒢 ↝ the node; `_default_provider()` (live-or-mock) |
| `IPP_object.py` | the Objects (Ω_k): `make_chat_handler` / `make_complete_handler` / `make_chat_stream_handler` bound by Γ to the provider |
| `IPP_executor.py` | the Executors (Ξ_k): `LLMExecutor` adds token + latency accounting to the hash-chained audit |

```python
from LLMs.IPP import llm_node
from general_tools.IPP_runtime import verify_node

node = llm_node()                        # live DeepSeek (mock fallback)
r = node.invoke("chat", [{"role": "user", "content": "hi"}])
print(r.payload["content"], r.payload["usage"])
node.executors["chat"].audit_verify()    # hash-chain check
verify_node(node) or "ALL 17 OK"         # the 17 invariants
```

## What it does

- **`DeepSeekProvider`** — wraps the OpenAI SDK against
  `https://api.deepseek.com` (model `deepseek-v4-flash` by default, configurable
  via `tools/config.py` + `LLMs/.env`). Implements the IPP transform
  `(messages + tools) → Φ → result`, plus true streaming
  (`chat_stream()` yielding `("thinking", …)`, `("text", …)`,
  `("tool_delta", …)` tuples and returning an `LLMResult` via PEP 380).
- **`MockProvider`** — deterministic offline fallback (no network): keyword
  templated answers + tool-call simulation, so demos/tests run without an API
  key.
- **`LLMResult`** — minimal envelope: `content`, `tool_calls`, `usage`,
  `thinking` (reasoning_content).

## Usage

```python
from LLMs.deepseek import DeepSeekProvider, MockProvider
# or via the unified facade:
from LLMs.api import DeepSeekProvider

llm = DeepSeekProvider()          # needs DEEPSEEK_API_KEY in LLMs/.env
result = llm.chat(messages=[{"role": "user", "content": "hi"}])
print(result.content)

offline = MockProvider()          # no key needed
```

## Where it's used

- `tools/engine.py` — `AgentEngine` (default provider + streaming)
- `codex_growth/`, `codex_RAG/`, `codex_normal/` — the three agents
- `ui/server.py`, `ui/gradio_chat.py` — web + chat UI
- `tools/codex_tools.py` — `tool_spawn_agent` offline fallback
- `LLMs/IPP.py` — the LLM IPP node channels (`chat` / `complete` / `chat_stream`)

## Config & credentials

The `.env` lives in `LLMs/.env` (gitignored) and is loaded by
`tools/config.py` (`Config.api_key()`, `Config.get_model()`). Never commit it.
