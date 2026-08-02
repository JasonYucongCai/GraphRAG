"""
LLMs/grok/provider.py — Grok LLM Provider (xAI API)

Wraps the OpenAI-compatible xAI API for Grok models.
Uses the same OpenAI SDK as DeepSeek but points to api.x.ai.

Supported models (as of July 2026):
  - grok-4: Latest Grok model
  - grok-3: Grok 3
  - grok-3-fast: Faster, lighter Grok 3 variant

API endpoint: https://api.x.ai/v1
Docs: https://docs.x.ai
"""

import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger("llms.grok")


class GrokProvider:
    """LLM provider for the xAI Grok API.

    OpenAI-compatible endpoint, same interface as DeepSeekProvider.

    Usage:
        provider = GrokProvider()
        response = provider.create_completion(
            messages=[{"role": "user", "content": "Hello"}],
            tools=[...],
        )

        # Or with a specific model:
        provider = GrokProvider(model="grok-3-fast")
    """

    # Default configuration
    DEFAULT_BASE_URL = "https://api.x.ai/v1"
    DEFAULT_MODEL = "grok-4"

    AVAILABLE_MODELS = [
        {"id": "grok-4", "name": "Grok 4",
         "desc": "Latest Grok model — most capable"},
        {"id": "grok-3", "name": "Grok 3",
         "desc": "Grok 3 — balanced performance"},
        {"id": "grok-3-fast", "name": "Grok 3 Fast",
         "desc": "Grok 3 Fast — faster, lighter variant"},
    ]

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize the Grok client.

        Args:
            model: Model ID (default: 'grok-4').
            api_key: xAI API key. Falls back to GROK_API_KEY env var.
            base_url: API base URL. Falls back to https://api.x.ai/v1.
        """
        import os

        self._api_key = api_key or os.getenv("GROK_API_KEY", "")
        self._base_url = base_url or os.getenv("GROK_BASE_URL", self.DEFAULT_BASE_URL)

        if self._api_key:
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        else:
            self._client = None
            logger.warning("No GROK_API_KEY set — Grok provider will be unavailable")

        self.model = model or os.getenv("GROK_MODEL", self.DEFAULT_MODEL)

    @property
    def is_available(self) -> bool:
        """Check if the provider has valid credentials."""
        return self._client is not None and bool(self._api_key)

    def switch_model(self, model_id: str) -> None:
        """Switch to a different model at runtime."""
        valid_ids = [m["id"] for m in self.AVAILABLE_MODELS]
        if model_id in valid_ids:
            self.model = model_id
        else:
            logger.warning(f"Unknown Grok model: {model_id}")

    def create_completion(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        """Call the Grok chat completions API.

        Args:
            messages: Conversation messages in OpenAI format.
            tools: Optional function-calling tool definitions.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens in the response.

        Returns:
            OpenAI ChatCompletion response object.

        Raises:
            RuntimeError: If no API key is configured.
            Exception: On API failure.
        """
        if not self._client:
            raise RuntimeError(
                "Grok provider is not available. Set GROK_API_KEY in LLMs/.env "
                "or pass api_key to GrokProvider()."
            )

        api_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            api_kwargs["tools"] = tools

        return self._client.chat.completions.create(**api_kwargs)
