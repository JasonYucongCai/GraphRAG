"""
graph_agent.types — shared agent type definitions (canonical home).

ToolCallEvent and ToolContext were previously co-located with the legacy
IPP abstraction in general_tools/IPP.py.  They are now the canonical types
of the agent engine and live here, next to AgentEngine.

All consumers should import from graph_agent:

    from graph_agent import AgentEngine, ToolCallEvent, ToolContext
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolContext:
    """Per-invocation context passed through the agent's tool-dispatch pipeline."""

    workspace_root: str = ""
    session_id: str = ""
    node_id: Any = None            # the graph node the agent is operating on
    local_graph: Any = None        # materialized local graph (L_3(u))
    encoder: Any = None            # encoder layer
    agent: Any = None              # back-reference to the owning agent
    extra: dict = field(default_factory=dict)


class ToolCallEvent:
    """Emitted at every key node of the agent loop, forming an auditable trace."""

    def __init__(
        self,
        type: str,  # start|tool_call|tool_result|text|thinking|message_delta|error|done
        tool: Optional[str] = None,
        args: Optional[dict] = None,
        content: Optional[str] = None,
        rounds: Optional[int] = None,
        usage: Optional[dict] = None,
        error: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        import time as _time

        self.type = type
        self.tool = tool
        self.args = args
        self.content = content
        self.rounds = rounds
        self.usage = usage
        self.error = error
        self.timestamp = timestamp or _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime())

    def __repr__(self) -> str:
        return f"<ToolCallEvent {self.type} tool={self.tool} content={str(self.content)[:60]!r}>"
