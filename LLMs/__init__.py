"""
LLMs — the LLM provider node, a strict IPP v0.2.8 component.

The canonical way to call an LLM in this platform is through the IPP node:

    from LLMs import llm_node, llm_chat

    node = llm_node()                           # Γ ⊩ LLMs/IPP.json × 𝒢
    result = node.invoke("chat", {"messages": [...]})  # guardrail envelope + audit
    text = result.payload["content"]

    # convenience:
    text = llm_chat(node, [{"role": "user", "content": "hi"}])

The raw DeepSeekProvider and MockProvider live in LLMs/deepseek/provider.py
and are INTERNAL to the IPP node — agents should NEVER import them directly.
"""
from LLMs.IPP import llm_node, llm_chat
from LLMs.deepseek.provider import LLMResult  # type envelope only

__all__ = ["llm_node", "llm_chat", "LLMResult"]
