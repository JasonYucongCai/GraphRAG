# LLMs/grok/ — Grok LLM Provider (xAI API)

OpenAI-compatible wrapper for SpaceXAI's xAI Grok API.

## Supported Models

| Model | Description |
|-------|-------------|
| `grok-4` | Latest Grok model — most capable |
| `grok-3` | Grok 3 — balanced performance |
| `grok-3-fast` | Grok 3 Fast — faster, lighter variant |

## Configuration

Add to `LLMs/.env`:

```ini
# Grok xAI API
GROK_API_KEY=xai-your-key-here
GROK_MODEL=grok-4
# GROK_MODEL=grok-3-fast    # Faster, cheaper
GROK_BASE_URL=https://api.x.ai/v1
```

Get a key at: https://docs.x.ai

## Usage

```python
from LLMs.grok import GrokProvider

provider = GrokProvider(model="grok-4")  # or grok-3, grok-3-fast

# Create a completion
response = provider.create_completion(
    messages=[{"role": "user", "content": "Hello, Grok!"}],
    tools=[...],           # Optional function-calling tools
    temperature=0.3,
    max_tokens=4096,
)

# Check availability
if provider.is_available:
    print("Grok provider ready")

# Switch models at runtime
provider.switch_model("grok-3-fast")
```

## API Endpoint

- Base URL: `https://api.x.ai/v1` (OpenAI-compatible)
- API key required: set via `GROK_API_KEY` env var or pass to constructor
