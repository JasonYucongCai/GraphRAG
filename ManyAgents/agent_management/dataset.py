"""
agents.dataset — the 20-agent dataset (one JSON file per agent).

The dataset folder (``agents/dataset/``) holds one JSON file per agent:
``Codex_01_Alice.json`` … ``Codex_20_Vivian.json``. Each file is the
agent's Agent Card — the three properties (capacity, random property,
constraints) plus discovery metadata and cross-agent comments.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from ManyAgents.agent_management.agent_card import AgentCard
from IPP_Social.paths import AGENTS_DATASET
from IPP_Social.util import atomic_write, read_text


class AgentDataset:
    """Read/write the agent cards as JSON files (thread-safe)."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else AGENTS_DATASET
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def card_path(self, agent_id: str) -> Path:
        return self.root / f"{agent_id}.json"

    def save_card(self, card: AgentCard) -> Path:
        """Persist one card as its JSON dataset file."""
        with self._lock:
            path = self.card_path(card.agent_id)
            atomic_write(path, json.dumps(card.to_dict(),
                                          ensure_ascii=False, indent=2))
            return path

    def load_card(self, agent_id: str) -> Optional[AgentCard]:
        with self._lock:
            path = self.card_path(agent_id)
            if not path.exists():
                return None
            return AgentCard.from_dict(
                json.loads(read_text(path)))

    def list_cards(self) -> list[AgentCard]:
        with self._lock:
            cards = []
            for path in sorted(self.root.glob("*.json")):
                try:
                    cards.append(AgentCard.from_dict(
                        json.loads(read_text(path))))
                except (json.JSONDecodeError, KeyError):
                    continue
            return cards

    def dataset_files(self) -> list[Path]:
        with self._lock:
            return sorted(self.root.glob("*.json"))
