"""
IPP_Social.paths — the canonical on-disk locations.

The **social database** is the data-only folder inside IPP_Social:
``social_database/`` holds the actual goals, the global chat board, the
event bus and the push inboxes. The **20-agent dataset** (one JSON file
per agent, containing the three properties + the Agent Card) lives in
``agents/dataset/``.
"""
from __future__ import annotations

from pathlib import Path

IPP_SOCIAL_ROOT = Path(__file__).resolve().parent

# ── the social database (data only) ─────────────────────────────────────
SOCIAL_DATABASE = IPP_SOCIAL_ROOT / "social_database"
GOALS_DIR = SOCIAL_DATABASE / "goals"       # <goal_id>/goal.md + <goal_id>/tasks/*.md
CHAT_DIR = SOCIAL_DATABASE / "chat"         # board.jsonl
EVENTS_DIR = SOCIAL_DATABASE / "events"     # events.jsonl
PUSH_DIR = SOCIAL_DATABASE / "push"         # subscriptions.json + <agent>/inbox.jsonl

# ── the 20-agent dataset (one JSON per agent) ───────────────────────────
AGENTS_DATASET = IPP_SOCIAL_ROOT / "agents" / "dataset"
