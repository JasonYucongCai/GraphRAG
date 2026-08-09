"""
swarm — the concurrent multi-agent runtime of the Multi Agent portal.

Each ManyAgents Codex agent gets its own IPP identity (finalized
engine/tools IPP.json), its own engine node + tools node constructed
into the shared GraphContext 𝒢, an AgentRuntime worker thread, and the
SwarmManager that runs many of them together under one goal.
"""
from __future__ import annotations

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
