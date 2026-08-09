"""
task_manager.goals — a goal is a folder.

``social_database/goals/<goal_id>/goal.md`` is the goal's metadata file
(JSON front-matter + human-readable body); its ``tasks/`` subfolder
holds the individual task Markdown files.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from IPP_Social.errors import DuplicateGoal, UnknownGoal
from IPP_Social.paths import GOALS_DIR
from IPP_Social.util import atomic_write, now_iso, read_text, slugify

GOAL_STATUSES: list[str] = ["open", "archived"]


class Goal:
    """A goal — one folder in the social database."""

    def __init__(self, goal_id: str, title: str, description: str = "",
                 owner_agent_id: str = "", status: str = "open",
                 created: str | None = None, updated: str | None = None):
        self.goal_id = goal_id
        self.title = title
        self.description = description
        self.owner_agent_id = owner_agent_id
        self.status = status
        self.created = created or now_iso()
        self.updated = updated or self.created

    def to_meta(self) -> dict:
        return {"goal_id": self.goal_id, "title": self.title,
                "description": self.description,
                "owner_agent_id": self.owner_agent_id,
                "status": self.status, "created": self.created,
                "updated": self.updated}

    @classmethod
    def from_meta(cls, m: dict) -> "Goal":
        return cls(goal_id=m.get("goal_id", ""), title=m.get("title", ""),
                   description=m.get("description", ""),
                   owner_agent_id=m.get("owner_agent_id", ""),
                   status=m.get("status", "open"),
                   created=m.get("created"), updated=m.get("updated"))

    def bump(self) -> None:
        self.updated = now_iso()


class GoalManager:
    """Create / list / get / archive goal folders (thread-safe)."""

    def __init__(self, root: Path | str | None = None):
        # root = the goals directory of the social database
        self.root = Path(root) if root else GOALS_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _folder(self, goal_id: str) -> Path:
        return self.root / goal_id

    def _goal_file(self, goal_id: str) -> Path:
        return self._folder(goal_id) / "goal.md"

    @staticmethod
    def _fence(meta: dict, body: str) -> str:
        return ("---\n" + json.dumps(meta, ensure_ascii=False, indent=2)
                + "\n---\n\n" + body)

    @staticmethod
    def _parse(text: str) -> tuple[dict, str]:
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end = next((i for i in range(1, len(lines))
                        if lines[i].strip() == "---"), None)
            if end is not None:
                return json.loads("\n".join(lines[1:end])), \
                    "\n".join(lines[end + 1:])
        return {}, text

    # ── ops ──────────────────────────────────────────────────────────────
    def create(self, title: str, description: str = "",
               owner_agent_id: str = "", goal_id: str | None = None) -> Goal:
        if not title:
            from IPP_Social.errors import SocialError
            raise SocialError("create_goal requires title", code="bad_request")
        if goal_id and self._goal_file(goal_id).exists():
            raise DuplicateGoal(f"goal {goal_id!r} already exists",
                                goal_id=goal_id)
        goal = Goal(goal_id=goal_id or self._unique_id(title),
                    title=title, description=description,
                    owner_agent_id=owner_agent_id)
        self.save(goal)
        return goal

    def list(self) -> list[Goal]:
        goals = []
        for path in sorted(self.root.glob("*/goal.md")):
            meta, _ = self._parse(read_text(path))
            goals.append(Goal.from_meta(meta))
        return goals

    def get(self, goal_id: str) -> Goal:
        path = self._goal_file(goal_id)
        if not path.exists():
            raise UnknownGoal(f"unknown goal {goal_id!r}", goal_id=goal_id)
        meta, _ = self._parse(read_text(path))
        return Goal.from_meta(meta)

    def archive(self, goal_id: str) -> Goal:
        goal = self.get(goal_id)
        goal.status = "archived"
        goal.bump()
        self.save(goal)
        return goal

    def delete(self, goal_id: str) -> None:
        """Permanently remove a goal folder and its task files."""
        folder = self._folder(goal_id)
        if not folder.exists():
            raise UnknownGoal(f"unknown goal {goal_id!r}", goal_id=goal_id)
        import shutil
        shutil.rmtree(folder)

    def save(self, goal: Goal) -> None:
        """Persist a goal's metadata file (front-matter + body)."""
        folder = self._folder(goal.goal_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "tasks").mkdir(exist_ok=True)
        body = f"# {goal.title}\n\n{goal.description or '(no description)'}"
        atomic_write(self._goal_file(goal.goal_id),
                     self._fence(goal.to_meta(), body))

    def _unique_id(self, title: str) -> str:
        base = slugify(title, "goal")
        existing = {g.goal_id for g in self.list()}
        cand, i = base, 2
        while cand in existing:
            cand = f"{base}-{i}"
            i += 1
        return cand
