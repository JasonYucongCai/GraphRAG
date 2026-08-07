"""
IPP_Social.settings — the Multi Agent platform settings (Settings tab).

Persisted in the social database (``social_database/settings.json``).
Defaults:

  llm_streaming     False — many agents default to NON-streaming LLM calls
                           (the streaming API serializes concurrent agents);
                           the Control Center Agent tab keeps streaming.
  max_concurrent    4     — parallel agent worker budget.
  social_responder  True  — agents auto-reply to messages addressed to them.
  max_reply_rounds  2     — conversation depth cap per (author, agent) pair.
  max_broadcast_responders 4 — how many agents may answer one broadcast
                           (prevents discussion storms).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from IPP_Social.paths import SOCIAL_DATABASE
from IPP_Social.util import atomic_write, read_text

DEFAULT_SETTINGS: dict = {
    "llm_streaming": False,
    "max_concurrent": 4,
    "social_responder": True,
    "max_reply_rounds": 2,
    "max_broadcast_responders": 4,
}

_VALID_KEYS = set(DEFAULT_SETTINGS)


class SettingsStore:
    """Thread-safe persisted settings (data: social_database/settings.json)."""

    def __init__(self, root: Optional[Path | str] = None):
        base = Path(root) if root else SOCIAL_DATABASE
        base.mkdir(parents=True, exist_ok=True)
        self._path = base / "settings.json"
        self._lock = threading.RLock()
        self._settings: dict = dict(DEFAULT_SETTINGS)
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(read_text(self._path))
            if isinstance(data, dict):
                for k in _VALID_KEYS:
                    if k in data:
                        self._settings[k] = data[k]
        except (json.JSONDecodeError, OSError):
            pass

    def get(self, key: str, default=None):
        with self._lock:
            return self._settings.get(key, default)

    def all(self) -> dict:
        with self._lock:
            return dict(self._settings)

    def update(self, changes: dict) -> dict:
        """Apply a partial update (unknown keys ignored); persists."""
        with self._lock:
            for k, v in (changes or {}).items():
                if k in _VALID_KEYS and v is not None:
                    self._settings[k] = v
            atomic_write(self._path, json.dumps(
                self._settings, ensure_ascii=False, indent=2))
            return dict(self._settings)
