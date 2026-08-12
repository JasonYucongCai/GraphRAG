"""
LLMs/grok — xAI Grok LLM provider (OpenAI-compatible).

An optional second LLM backend alongside DeepSeek. Uses the same
OpenAI-compatible interface via GrokProvider. Not activated by default
— the LLM IPP node (LLMs/IPP.py) uses DeepSeek as primary.

    from LLMs.grok import GrokProvider
    grok = GrokProvider()
"""
from LLMs.grok.provider import GrokProvider

__all__ = ["GrokProvider"]
