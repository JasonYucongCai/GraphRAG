"""
agents.constraints — property #3: the mutable physical state vector.

Position (x, y, z) plus additional resources. Every update must obey
the physical constraints of the social world:

  • each axis within WORLD_BOUNDS
  • |Δaxis| ≤ MAX_STEP_PER_UPDATE (no teleporting)
  • all resources non-negative

``apply_update`` validates first, then returns a NEW Constraints —
updates are immutable-style and logged in the VCL.
"""
from __future__ import annotations

from IPP_Social.errors import ConstraintViolation
from IPP_Social.util import now_iso

# ── the physical world ───────────────────────────────────────────────────
WORLD_BOUNDS: dict[str, float] = {"min": 0.0, "max": 100.0}
MAX_STEP_PER_UPDATE: float = 10.0     # no teleporting
DEFAULT_RESOURCES: dict[str, float] = {"energy": 100.0, "compute": 10.0}


class Constraints:
    """Physical state: position (x, y, z) + resources, validated."""

    def __init__(self, position: dict | None = None,
                 resources: dict | None = None,
                 version: int = 1, updated_by: str = "",
                 vcl: list | None = None):
        self.position: dict[str, float] = {
            k: float((position or {}).get(k, 0.0)) for k in ("x", "y", "z")}
        self.resources: dict[str, float] = {
            k: float(v) for k, v in
            (resources or dict(DEFAULT_RESOURCES)).items()}
        self.version = int(version)
        self.updated_by = updated_by
        self.vcl: list[str] = list(vcl or [])

    def to_dict(self) -> dict:
        return {
            "position": {k: round(float(self.position.get(k, 0.0)), 2)
                         for k in ("x", "y", "z")},
            "resources": {k: round(float(v), 2)
                          for k, v in self.resources.items()},
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "Constraints":
        d = d or {}
        return cls(position=d.get("position"),
                   resources=d.get("resources"),
                   version=int(d.get("version", 1)))

    # ── physical validation ──────────────────────────────────────────────
    def validate_update(self, position: dict, resources: dict) -> None:
        """Raise ConstraintViolation on any physical rule breach."""
        problems: list[str] = []
        pos = {k: float(position.get(k, self.position.get(k, 0.0)))
               for k in ("x", "y", "z")}
        for axis in ("x", "y", "z"):
            v = pos[axis]
            if not (WORLD_BOUNDS["min"] <= v <= WORLD_BOUNDS["max"]):
                problems.append(
                    f"{axis}={v} outside world bounds "
                    f"[{WORLD_BOUNDS['min']}, {WORLD_BOUNDS['max']}]")
            step = abs(v - self.position[axis])
            if step > MAX_STEP_PER_UPDATE:
                problems.append(
                    f"|Δ{axis}|={step:.1f} exceeds max step "
                    f"{MAX_STEP_PER_UPDATE} (no teleporting)")
        merged = dict(self.resources)
        for k, v in (resources or {}).items():
            if not isinstance(v, (int, float)):
                problems.append(f"resource {k!r} is not numeric")
            elif v < 0.0:
                problems.append(f"resource {k}={v} is negative")
            else:
                merged[k] = float(v)
        if problems:
            raise ConstraintViolation(
                "physical constraints violated: " + "; ".join(problems),
                violations=problems)

    def apply_update(self, agent_id: str, position: dict | None = None,
                     resources: dict | None = None) -> "Constraints":
        """Validate then apply; returns a NEW Constraints (immutable style)."""
        self.validate_update(position or {}, resources or {})
        new_pos = {k: float((position or {}).get(k, self.position[k]))
                   for k in ("x", "y", "z")}
        new_res = dict(self.resources)
        new_res.update({k: float(v) for k, v in (resources or {}).items()})
        c = Constraints(position=new_pos, resources=new_res,
                        version=self.version + 1, updated_by=agent_id,
                        vcl=list(self.vcl))
        c.vcl.append(f"{now_iso()}: position={new_pos} "
                     f"resources={new_res} by {agent_id}")
        return c
