"""
LLMs/deepseek — INTERNAL DeepSeek HTTP client. NOT a public API.

The raw provider (DeepSeekProvider, MockProvider) is consumed ONLY by the
IPP node's Ω handlers (LLMs/IPP_object.py). Agents should call the LLM
through the IPP node:

    from LLMs import llm_node
    node = llm_node()
    result = node.invoke("chat", {"messages": [...]})

Direct imports of DeepSeekProvider by agents or tools are a BYPASS of the
IPP guardrail envelope and should be migrated to IPP node invocation.
"""
from LLMs.deepseek.provider import LLMResult, DeepSeekProvider, MockProvider  # noqa: F401 — internal, for IPP handlers

__all__ = ["LLMResult", "DeepSeekProvider", "MockProvider"]
