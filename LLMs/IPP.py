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
import threading
from pathlib import Path
from typing import Optional

from IPP.IPP_constructor import IPPConstructor
from IPP.IPP_registry import GraphContext

logger = logging.getLogger("LLMs.IPP")

_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"

# ── singleton (process-wide) ─────────────────────────────────────────────
_lock = threading.RLock()
_NODE = None
_CTX = None
_PROVIDER = None


def _default_provider():
    """Live DeepSeek if the key works, else the deterministic MockProvider.
    Result is cached so the live-ping happens at most once per process."""
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER
    from LLMs.deepseek import DeepSeekProvider, MockProvider
    try:
        p = DeepSeekProvider()
        p.chat([{"role": "user", "content": "ping"}], max_tokens=4)
        logger.info("LLM node: deepseek:%s (live)", p.model)
        _PROVIDER = p
        return p
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM node: DeepSeek unavailable (%s) → MockProvider", exc)
        _PROVIDER = MockProvider()
        return _PROVIDER


def llm_node(provider=None, context=None,
             constructor=None):
    """The process-wide singleton LLM node (lazy construction).

    First call constructs the node; later calls return the same instance —
    one node, one audit trail.  If a *context* is provided, the node is
    also registered into that context's registry (so it can be resolved
    as an upstream/downstream partner even when the context differs from
    the construction context).
    """
    global _NODE, _CTX
    with _lock:
        if _NODE is None:
            ctx = context or GraphContext()
            p = provider or _default_provider()
            if "provider" not in ctx.bindings:
                ctx.bind("provider", p)
            from LLMs.IPP_executor import LLMExecutor
            gamma = constructor or IPPConstructor(
                ctx, executor_classes={ch: LLMExecutor
                                       for ch in ("chat", "complete", "chat_stream")})
            _NODE = gamma.construct_file(_IPP_JSON, ctx)
            gamma.recall_scope(_NODE)
            ctx.register_node(_NODE)
            _CTX = ctx
            logger.info("LLM IPP node constructed: llm (3 channels)")
        # Register into the provided context even when already constructed
        if context is not None and _NODE is not None:
            context.register_node(_NODE)
        return _NODE


def reset_llm_node() -> None:
    """Drop the singleton node (tests)."""
    global _NODE, _CTX, _PROVIDER
    with _lock:
        _NODE, _CTX, _PROVIDER = None, None, None


def llm_chat(node, messages: list, **kwargs) -> dict:
    """Convenience: invoke the chat channel and return the LLMResult dict."""
    payload = {"messages": messages, **kwargs}
    return node.invoke("chat", payload).payload
