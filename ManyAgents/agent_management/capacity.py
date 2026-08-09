"""
agents.capacity — property #1: capacity (the identity).

A ten-dimensional score vector (0–100) describing what the agent can
do. Fixed at registration — it is the agent's identity, not its mood.
"""
from __future__ import annotations

from IPP_Social.errors import ConstraintViolation, SocialError

# The ten canonical capability dimensions
DIMENSIONS: list[str] = [
    "math",            # formal manipulation, numerics, proof
    "physics",         # physical intuition, mechanics, dynamics
    "engineering",     # building, systems, tooling, robustness
    "biology",         # life-science knowledge
    "genomics",        # sequence analysis, genetics, omics
    "reasoning",       # logic, deduction, planning
    "research",        # literature, evidence, methods
    "social",          # interaction, coordination, communication
    "play",            # exploration, games, experimentation
    "creativity",      # novel combinations, style, invention
]

DIM_DEFAULT = 50.0     # neutral fill for missing dimensions


class Capacity:
    """Ten-dimensional identity score vector, fixed at registration."""

    def __init__(self, scores: dict | None = None):
        self.scores: dict[str, float] = {}
        for dim in DIMENSIONS:
            self.scores[dim] = float(scores.get(dim, DIM_DEFAULT)) \
                if scores else DIM_DEFAULT
        self.validate()

    def validate(self) -> None:
        for dim in DIMENSIONS:
            s = self.scores.get(dim)
            if s is None or not isinstance(s, (int, float)):
                raise SocialError(
                    f"capacity missing dimension {dim!r}", code="bad_capacity")
            if not 0.0 <= float(s) <= 100.0:
                raise ConstraintViolation(
                    f"capacity {dim} = {s} outside [0, 100]",
                    dimension=dim, value=s)

    def to_dict(self) -> dict:
        return {dim: round(float(self.scores[dim]), 2) for dim in DIMENSIONS}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Capacity":
        return cls({str(k): float(v) for k, v in (d or {}).items()})

    def __str__(self) -> str:
        return ", ".join(f"{d}={v:.0f}" for d, v in self.to_dict().items())
