"""
agent_management - agent identity, cards, and datasets.

Moved from IPP_Social/agents/ to ManyAgents/agent_management/.
"""
from ManyAgents.agent_management.agent_card import AgentCard, Comment
from ManyAgents.agent_management.capacity import DIMENSIONS, Capacity
from ManyAgents.agent_management.constraints import (
    Constraints, WORLD_BOUNDS, MAX_STEP_PER_UPDATE, DEFAULT_RESOURCES,
)
from ManyAgents.agent_management.dataset import AGENTS_DATASET, AgentDataset
from ManyAgents.agent_management.random_property import RANDOM_DEFAULT, RandomProperty

__all__ = [
    "AgentCard", "Comment",
    "DIMENSIONS", "Capacity",
    "Constraints", "WORLD_BOUNDS", "MAX_STEP_PER_UPDATE", "DEFAULT_RESOURCES",
    "AGENTS_DATASET", "AgentDataset",
    "RANDOM_DEFAULT", "RandomProperty",
]
