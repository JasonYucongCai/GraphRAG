"""
agents.random_property — property #2: the stochastic trait vector.

A ten-dimensional vector; each dimension carries ``{mean, variance}``.
Sampling the vector produces a momentary tendency for each dimension —
a "mention" — ``N(mean, sqrt(variance))`` clamped to [0, 100].
"""
from __future__ import annotations

import math
import random

from ManyAgents.agent_management.capacity import DIMENSIONS
from IPP_Social.errors import ConstraintViolation

RANDOM_DEFAULT = {"mean": 50.0, "variance": 5.0}


class RandomProperty:
    """Ten-dimensional {mean, variance} trait vector (the mentions)."""

    def __init__(self, traits: dict | None = None):
        self.traits: dict[str, dict] = {}
        for dim in DIMENSIONS:
            t = (traits or {}).get(dim)
            if not isinstance(t, dict):
                t = dict(RANDOM_DEFAULT)
            self.traits[dim] = {
                "mean": float(t.get("mean", RANDOM_DEFAULT["mean"])),
                "variance": float(t.get("variance",
                                        RANDOM_DEFAULT["variance"])),
            }
        self.validate()

    def validate(self) -> None:
        for dim, t in self.traits.items():
            if not 0.0 <= t["mean"] <= 100.0:
                raise ConstraintViolation(
                    f"random property {dim}.mean = {t['mean']} outside "
                    "[0, 100]", dimension=dim)
            if t["variance"] < 0.0:
                raise ConstraintViolation(
                    f"random property {dim}.variance = {t['variance']} < 0",
                    dimension=dim)

    def sample(self, seed: int | None = None) -> dict[str, float]:
        """One momentary tendency vector — a "mention" of each trait."""
        rng = random.Random(seed)
        out: dict[str, float] = {}
        for dim, t in self.traits.items():
            z = rng.gauss(0.0, 1.0)
            v = t["mean"] + z * math.sqrt(t["variance"])
            out[dim] = round(min(100.0, max(0.0, v)), 2)
        return out

    def to_dict(self) -> dict:
        return {dim: {"mean": round(t["mean"], 2),
                      "variance": round(t["variance"], 2)}
                for dim, t in self.traits.items()}

    @classmethod
    def from_dict(cls, d: dict | None) -> "RandomProperty":
        return cls({str(k): v for k, v in (d or {}).items()})
