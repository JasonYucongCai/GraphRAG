"""
ManyAgents — the Multi Agent platform, a strict IPP v0.2.8 component.

A single unified IPP node (IPP.json + IPP_object.py + IPP_executor.py)
with two channels: `cards` (agent card CRUD) and `orchestrate` (swarm
lifecycle). Sub-packages provide domain types and runtime machinery.

Construct via Γ (IPPConstructor):
    from IPP.IPP_constructor import IPPConstructor
    from ManyAgents.IPP_executor import ManyAgentsExecutor
    gamma = IPPConstructor(executor_classes={ch: ManyAgentsExecutor for ch in ...})
    gamma.context.bind("dataset", dataset)
    gamma.context.bind("swarm", swarm)
    node = gamma.construct_file("ManyAgents/IPP.json")
"""
from ManyAgents.swarm import (
    SwarmBus, AgentRuntime, SwarmManager,
    build_engine, construct_agent_nodes,
    finalize_agent_ipp, finalize_all_agents, list_agent_folders,
    LIVE_CHAT_STREAM_HANDLER,
)
from ManyAgents.agent_management import AgentCard, AgentDataset

__all__ = [
    "SwarmBus", "AgentRuntime", "SwarmManager",
    "build_engine", "construct_agent_nodes",
    "finalize_agent_ipp", "finalize_all_agents", "list_agent_folders",
    "LIVE_CHAT_STREAM_HANDLER",
    "AgentCard", "AgentDataset",
]
