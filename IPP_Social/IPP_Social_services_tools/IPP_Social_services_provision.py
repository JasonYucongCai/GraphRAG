"""
social_activity.provision — generate the 20-agent dataset from ManyAgents.

Scans ``ManyAgents/Codex_*`` folders, reads each agent's
``system_prompt.md`` (identity + personality), and writes one JSON
dataset file per agent (the Agent Card with the three properties):
``agents/dataset/Codex_XX_Name.json``.

CLI::

    python -m IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision [--dataset-root DIR]
        [--agents-root DIR] [--overwrite] [--list]
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Optional

from ManyAgents.agent_management.agent_card import AgentCard
from ManyAgents.agent_management.capacity import DIMENSIONS, Capacity
from ManyAgents.agent_management.constraints import (
    DEFAULT_RESOURCES, Constraints, WORLD_BOUNDS,
)
from ManyAgents.agent_management.dataset import AgentDataset
from ManyAgents.agent_management.random_property import RandomProperty

MANY_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "ManyAgents"

# personality keywords → dimension boosts (applied per occurrence)
KEYWORD_BOOSTS: dict[str, dict[str, float]] = {
    "bold": {"play": 6, "social": 4, "reasoning": 3},
    "dynamic": {"play": 6, "social": 4, "creativity": 3},
    "decisive": {"reasoning": 5, "engineering": 5, "play": 3},
    "warm": {"social": 9},
    "friendly": {"social": 8},
    "sociable": {"social": 8},
    "engaging": {"social": 7, "creativity": 3},
    "curious": {"research": 8, "reasoning": 4},
    "inquisitive": {"research": 8, "reasoning": 3},
    "questions": {"research": 6},
    "creative": {"creativity": 9},
    "calm": {"reasoning": 6},
    "steady": {"engineering": 5, "reasoning": 3},
    "composed": {"reasoning": 5},
    "energetic": {"play": 6, "social": 5},
    "spirited": {"play": 7, "social": 4},
    "vibrant": {"play": 6, "social": 6, "creativity": 4},
    "lively": {"play": 6, "social": 5},
    "organized": {"engineering": 7},
    "planning": {"engineering": 6, "reasoning": 3},
    "practical": {"engineering": 6},
    "confident": {"social": 4, "play": 4},
    "optimistic": {"social": 6, "play": 4},
    "encouraging": {"social": 7},
    "motivating": {"social": 7},
    "cheerful": {"social": 6, "play": 3},
    "efficient": {"engineering": 6, "reasoning": 3},
    "driven": {"engineering": 5, "research": 3},
    "determined": {"engineering": 5, "reasoning": 4},
    "thoughtful": {"reasoning": 7},
    "science": {"research": 5, "physics": 3},
    "math": {"math": 5, "reasoning": 3},
    "physics": {"physics": 5},
    "engineering": {"engineering": 5},
    "biology": {"biology": 5},
    "genomics": {"genomics": 5},
    "research": {"research": 5},
    "play": {"play": 5},
}


def parse_system_prompt(path: Path) -> dict:
    """Extract {name, personality} from a Codex agent's system_prompt.md."""
    text = path.read_text(encoding="utf-8")
    name = ""
    m = re.search(r"\*\*Name:\*\*\s*\**([A-Za-z]+)\**", text)
    if m:
        name = m.group(1)
    personality = ""
    m = re.search(r"## Personality\s*\n(.*?)(?=\n## |\Z)", text, re.S)
    if m:
        personality = " ".join(m.group(1).split())
    return {"name": name, "personality": personality}


def build_profile(agent_id: str, name: str, personality: str) -> dict:
    """Seeded capacity + random property + constraints for one agent."""
    seed = hashlib.sha256(agent_id.encode("utf-8")).digest()
    rng = list(seed)

    def pick(i: int, lo: int, hi: int) -> int:
        return lo + (rng[i % len(rng)] % (hi - lo + 1))

    scores: dict[str, float] = {}
    for i, dim in enumerate(DIMENSIONS):
        scores[dim] = float(pick(i, 45, 90))
    # personality keyword boosts
    low = personality.lower()
    for keyword, boosts in KEYWORD_BOOSTS.items():
        if keyword in low:
            for dim, delta in boosts.items():
                scores[dim] = min(95.0, scores[dim] + delta)
    scores = {d: round(max(10.0, min(95.0, v)), 1)
              for d, v in scores.items()}

    traits: dict[str, dict] = {}
    for i, dim in enumerate(DIMENSIONS):
        offset = pick(20 + i, 0, 10) - 5          # ±5 around capacity
        mean = min(100.0, max(0.0, scores[dim] + offset))
        variance = float(pick(40 + i, 3, 17))     # 3..17 volatility
        traits[dim] = {"mean": round(mean, 1), "variance": variance}

    lo, hi = int(WORLD_BOUNDS["min"]), int(WORLD_BOUNDS["max"])
    position = {"x": float(pick(60, lo, hi)),
                "y": float(pick(61, lo, hi)),
                "z": float(pick(62, lo, hi))}
    return {
        "capacity": Capacity(scores),
        "random_property": RandomProperty(traits),
        "constraints": Constraints(position=position,
                                   resources=dict(DEFAULT_RESOURCES)),
        "bio": personality,
    }


def provision_many_agents(dataset: AgentDataset,
                          many_agents_root: Optional[Path] = None,
                          overwrite: bool = False) -> list[dict]:
    """Write one JSON dataset file per ``ManyAgents/Codex_*`` agent.

    Returns the list of written card summaries. Existing cards are
    skipped unless ``overwrite`` is set.
    """
    root = Path(many_agents_root or MANY_AGENTS_ROOT)
    written: list[dict] = []
    # `Codex_[0-9]*` avoids matching codex_normal / codex_normal copy
    # (pathlib glob is case-insensitive on Windows)
    for folder in sorted(root.glob("Codex_[0-9]*")):
        if not folder.is_dir():
            continue
        prompt = folder / "system_prompt.md"
        if not prompt.exists():
            continue
        agent_id = folder.name
        parsed = parse_system_prompt(prompt)
        name = parsed["name"] or agent_id.split("_", 2)[-1]
        profile = build_profile(agent_id, name, parsed["personality"])
        if dataset.load_card(agent_id) is not None and not overwrite:
            continue
        card = AgentCard(
            agent_id=agent_id, name=name,
            capacity=profile["capacity"],
            random_property=profile["random_property"],
            constraints=profile["constraints"],
            bio=profile["bio"],
        )
        card.vcl.append(f"{card.created}: registered via provision_many_agents")
        path = dataset.save_card(card)
        written.append({"agent_id": agent_id, "name": name, "file": str(path)})
    return written


def _cli() -> None:
    ap = argparse.ArgumentParser(
        description="Generate the 20-agent dataset from ManyAgents")
    ap.add_argument("--dataset-root", default=None,
                    help="dataset folder (default: agents/dataset)")
    ap.add_argument("--agents-root", default=None,
                    help="ManyAgents root (default: ../../ManyAgents)")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite existing cards")
    ap.add_argument("--list", action="store_true",
                    help="list dataset cards after provisioning")
    args = ap.parse_args()

    dataset = AgentDataset(args.dataset_root)
    many = Path(args.agents_root) if args.agents_root else MANY_AGENTS_ROOT
    written = provision_many_agents(dataset, many, args.overwrite)
    print(f"provisioned {len(written)} agents into {dataset.root}")
    if args.list:
        for card in sorted(dataset.list_cards(), key=lambda c: c.agent_id):
            top = ", ".join(f"{d}={card.capacity.scores[d]:.0f}"
                            for d in sorted(
                                card.capacity.scores,
                                key=card.capacity.scores.get, reverse=True)[:3])
            pos = card.constraints.position
            print(f"  {card.agent_id:<22} {card.name:<10} "
                  f"top: {top:<44} pos=({pos['x']:.0f},{pos['y']:.0f},"
                  f"{pos['z']:.0f})")


if __name__ == "__main__":
    _cli()
