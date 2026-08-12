"""
general_tools.engine — deprecated re-export (backward compatibility only).

The AgentEngine now lives at graph_agent/engine.py (its canonical IPP home).
New code MUST import from graph_agent directly:

    from graph_agent import AgentEngine, ToolCallEvent, ToolContext

This file is kept so existing external consumers don't break immediately,
but it WILL be removed in a future version.
"""
import warnings

from graph_agent.engine import AgentEngine, LLMResult, _LLMNodeAdapter  # noqa: F401

__all__ = ["AgentEngine", "LLMResult"]

warnings.warn(
    "general_tools.engine is deprecated; import from graph_agent instead",
    DeprecationWarning, stacklevel=2,
)
