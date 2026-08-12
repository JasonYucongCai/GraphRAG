"""
swarm — the concurrent multi-agent runtime.

AgentRuntime workers, SwarmManager orchestration, SwarmBus for live SSE
events, SocialResponder for the conversation loop, and the live chat-stream
handler bound into per-agent engine nodes.
"""
from ManyAgents.swarm.agent_ipp import (
    LIVE_CHAT_STREAM_HANDLER, build_engine, construct_agent_nodes,
    finalize_agent_ipp, finalize_all_agents, list_agent_folders,
)
from ManyAgents.swarm.bus import SwarmBus
from ManyAgents.swarm.runtime import AgentRuntime
from ManyAgents.swarm.swarm import SwarmManager

__all__ = [
    "SwarmBus", "AgentRuntime", "SwarmManager",
    "finalize_agent_ipp", "finalize_all_agents", "list_agent_folders",
    "construct_agent_nodes", "build_engine", "LIVE_CHAT_STREAM_HANDLER",
]
