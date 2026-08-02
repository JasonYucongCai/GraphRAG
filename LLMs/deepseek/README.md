# LLMs/deepseek/ — DeepSeek Provider Scripts

Everything the agents use to talk to DeepSeek's OpenAI-compatible Chat
Completions API lives in this subfolder.

## Files

| File | Role |
|---|---|
| `provider.py` | `LLMResult` (ChatCompletion-like envelope), `DeepSeekProvider` (live, IPP), `MockProvider` (offline, deterministic) |
| `__init__.py` | re-exports `LLMResult`, `DeepSeekProvider`, `MockProvider` |

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

## Config & credentials

The `.env` lives in `LLMs/.env` (gitignored) and is loaded by
`tools/config.py` (`Config.api_key()`, `Config.get_model()`). Never commit it.
