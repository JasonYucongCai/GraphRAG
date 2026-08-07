"""
agents — property #1–3 of a social agent + the Agent Card + the dataset.

The three agent properties:

  1. **Capacity**        — the *identity* of what the agent can do,
     evaluated in 10 dimensions (math, physics, engineering, biology,
     genomics, reasoning, research, social, play, creativity).
  2. **RandomProperty**  — a 10-dimensional trait vector; each dimension
     holds a ``{mean, variance}``; sampling it produces the agent's
     momentary tendency ("mention") per dimension.
  3. **Constraints**     — the *mutable* physical state vector:
     position (x, y, z) + additional resources, obeying the physical
     constraints of the social world.

The Agent Card (one JSON file per agent) bundles the three properties
with the discovery metadata and cross-agent comments; the dataset of 20
agents lives in ``agents/dataset/`` (one JSON per agent).
"""
from __future__ import annotations

from IPP_Social.agents.agent_card import AgentCard, Comment
from IPP_Social.agents.capacity import DIMENSIONS, Capacity
from IPP_Social.agents.constraints import (
    DEFAULT_RESOURCES, MAX_STEP_PER_UPDATE, WORLD_BOUNDS, Constraints,
)
from IPP_Social.agents.dataset import AGENTS_DATASET, AgentDataset
from IPP_Social.agents.random_property import RANDOM_DEFAULT, RandomProperty

__all__ = [
    "DIMENSIONS", "Capacity", "RandomProperty", "RANDOM_DEFAULT",
    "Constraints", "WORLD_BOUNDS", "MAX_STEP_PER_UPDATE",
    "DEFAULT_RESOURCES", "AgentCard", "Comment", "AgentDataset",
    "AGENTS_DATASET",
]
