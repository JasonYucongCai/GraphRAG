"""
LLMs API — public interface for the LLM providers package.

The single entry point for LLM providers. DeepSeek lives in
LLMs/deepseek/provider.py (LLMResult, DeepSeekProvider, MockProvider);
Grok is the optional second provider.
"""

from LLMs.deepseek import LLMResult, DeepSeekProvider, MockProvider

# Grok provider (lazy to avoid import errors if xAI key not set)
_GROK_AVAILABLE = False
try:
    from LLMs.grok import GrokProvider
    _GROK_AVAILABLE = True
except ImportError:
    GrokProvider = None

__all__ = ["LLMResult", "DeepSeekProvider", "MockProvider", "GrokProvider"]
