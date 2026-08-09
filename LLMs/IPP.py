"""
LLMs.IPP — construct the LLM node per IPP v0.2.8.

Public API:

    from LLMs.IPP import llm_node

    node = llm_node()                       # live DeepSeek (mock fallback)
    r = node.invoke("chat", [{"role": "user", "content": "Reply: OK"}])
    print(r.payload["content"])             # LLMResult dict
    node.executors["chat"].audit_verify()   # hash chain check

The node is constructed by Γ (IPP.IPP_constructor) from LLMs/IPP.json, with the
provider bound into the GraphContext (bindings["provider"]).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from IPP.IPP_constructor import IPPConstructor
from IPP.IPP_registry import GraphContext

logger = logging.getLogger("LLMs.IPP")

_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"


def _default_provider():
    """Live DeepSeek if the key works, else the deterministic MockProvider."""
    from LLMs.deepseek import DeepSeekProvider, MockProvider
    try:
        p = DeepSeekProvider()
        p.chat([{"role": "user", "content": "ping"}], max_tokens=4)
        logger.info("LLM node: deepseek:%s (live)", p.model)
        return p
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM node: DeepSeek unavailable (%s) → MockProvider", exc)
        return MockProvider()


def llm_node(provider=None, context: Optional[GraphContext] = None,
             constructor: Optional[IPPConstructor] = None):
    """Γ ⊩ LLMs/IPP.json × 𝒢 ↝ ((Ω_k, Ξ_k)) — the LLM node.

    Args:
        provider: a DeepSeekProvider / MockProvider (default: live-or-mock).
        context:  GraphContext 𝒢 (a fresh one is created and bound).
        constructor: an IPPConstructor Γ (fresh if omitted).
    """
    ctx = context or GraphContext()
    if "provider" not in ctx.bindings:
        ctx.bind("provider", provider or _default_provider())
    from LLMs.IPP_executor import LLMExecutor
    gamma = constructor or IPPConstructor(
        ctx, executor_classes={ch: LLMExecutor
                               for ch in ("chat", "complete", "chat_stream")})
    node = gamma.construct_file(_IPP_JSON, ctx)
    gamma.recall_scope(node)
    ctx.register_node(node)   # 𝒩: make the LLM node a resolution partner
    return node


def llm_chat(node, messages: list, **kwargs) -> dict:
    """Convenience: invoke the chat channel and return the LLMResult dict."""
    payload = {"messages": messages, **kwargs}
    return node.invoke("chat", payload).payload
