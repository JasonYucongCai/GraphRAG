"""
task_manager.tasks — individual tasks are Markdown files.

Each task lives at ``social_database/goals/<goal_id>/tasks/<task_id>.md``:
JSON front-matter (status, assignee, deps) + a body with ``## Notes``
and a ``## Version Control Log`` at the bottom (repo convention).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from IPP_Social.errors import InvalidStatus, SocialError, UnknownGoal
from IPP_Social.paths import GOALS_DIR
from IPP_Social.util import atomic_write, now_iso, read_text, slugify

# A2A-flavoured task lifecycle
TASK_STATUSES: list[str] = [
    "submitted", "processing", "needs_input", "completed", "failed",
    "canceled",
]
TERMINAL_STATUSES: set[str] = {"completed", "failed", "canceled"}


class Task:
    """An individual collaborative task — a Markdown file in a goal folder."""

    def __init__(self, task_id: str, goal_id: str, title: str,
                 description: str = "", status: str = "submitted",
                 assignee_agent_id: str = "",
                 depends_on: list | None = None,
                 notes: list | None = None, vcl: list | None = None,
                 created: str | None = None, updated: str | None = None):
        self.task_id = task_id
        self.goal_id = goal_id
        self.title = title
        self.description = description
        self.status = status
        self.assignee_agent_id = assignee_agent_id
        self.depends_on: list[str] = list(depends_on or [])
        self.notes: list[str] = list(notes or [])
        self.vcl: list[str] = list(vcl or [])
        self.created = created or now_iso()
        self.updated = updated or self.created

    def to_meta(self) -> dict:
        return {"task_id": self.task_id, "goal_id": self.goal_id,
                "title": self.title, "status": self.status,
                "assignee_agent_id": self.assignee_agent_id,
                "depends_on": list(self.depends_on),
                "created": self.created, "updated": self.updated}

    @classmethod
    def from_meta(cls, m: dict) -> "Task":
        return cls(task_id=m.get("task_id", ""), goal_id=m.get("goal_id", ""),
                   title=m.get("title", ""),
                   status=m.get("status", "submitted"),
                   assignee_agent_id=m.get("assignee_agent_id", ""),
                   depends_on=list(m.get("depends_on", [])),
                   created=m.get("created"), updated=m.get("updated"))

    # ── collaboration ────────────────────────────────────────────────────
    def update(self, agent_id: str, status: Optional[str] = None,
               note: Optional[str] = None,
               assignee: Optional[str] = None) -> None:
        """Collaborative update: status / note / reassignment, all logged."""
        if status is not None:
            if status not in TASK_STATUSES:
                raise InvalidStatus(
                    f"status {status!r} not in {TASK_STATUSES}", status=status)
            self.status = status
        if assignee is not None:
            self.assignee_agent_id = assignee
        self.updated = now_iso()
        entry = f"{self.updated}: {agent_id}"
        if status is not None:
            entry += f" → status {status}"
        if assignee is not None:
            entry += f" → assignee {assignee}"
        if note:
            self.notes.append(f"{self.updated} ({agent_id}): {note}")
            entry += f" — note: {note}"
        self.vcl.append(entry)

    def body_md(self) -> str:
        parts = [f"# {self.title}", "", self.description or "(no description)",
                 "", "## Notes"]
        parts += [f"- {n}" for n in self.notes]
        parts += ["", "## Version Control Log"]
        parts += [f"- {v}" for v in self.vcl]
        return "\n".join(parts)


class TaskManager:
    """Create / update / get / list task Markdown files (thread-safe)."""

    def __init__(self, goals_root: Path | str | None = None):
        # the SAME root as GoalManager: the goals directory of the database
        self.goals_root = Path(goals_root) if goals_root else GOALS_DIR
        self._lock = threading.RLock()

    def _tasks_dir(self, goal_id: str) -> Path:
        return self.goals_root / goal_id / "tasks"

    def _task_file(self, goal_id: str, task_id: str) -> Path:
        return self._tasks_dir(goal_id) / f"{task_id}.md"

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

    def _ensure_goal(self, goal_id: str) -> None:
        if not (self.goals_root / goal_id / "goal.md").exists():
            raise UnknownGoal(f"unknown goal {goal_id!r}", goal_id=goal_id)

    # ── ops ──────────────────────────────────────────────────────────────
    def create(self, goal_id: str, title: str, description: str = "",
               assignee_agent_id: str = "", task_id: str | None = None,
               author_agent_id: str = "",
               depends_on: list | None = None,
               status: str = "submitted") -> Task:
        self._ensure_goal(goal_id)
        if not title:
            raise SocialError("create_task requires title", code="bad_request")
        task = Task(
            task_id=task_id or self._unique_id(goal_id, title),
            goal_id=goal_id, title=title, description=description,
            status=status, assignee_agent_id=assignee_agent_id,
            depends_on=list(depends_on or []),
        )
        task.vcl.append(f"{task.created}: created by "
                        f"{author_agent_id or 'unknown'}")
        self.save(task)
        return task

    def save(self, task: Task) -> None:
        folder = self._tasks_dir(task.goal_id)
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write(self._task_file(task.goal_id, task.task_id),
                     self._fence(task.to_meta(), task.body_md()))

    def update(self, goal_id: str, task_id: str, agent_id: str,
               status: Optional[str] = None, note: Optional[str] = None,
               assignee: Optional[str] = None) -> Task:
        task = self.get(goal_id, task_id)
        task.update(agent_id, status=status, note=note, assignee=assignee)
        self.save(task)
        return task

    def get(self, goal_id: str, task_id: str) -> Task:
        path = self._task_file(goal_id, task_id)
        if not path.exists():
            raise SocialError(f"unknown task {task_id!r} in {goal_id!r}",
                              code="unknown_task", goal_id=goal_id,
                              task_id=task_id)
        meta, body = self._parse(read_text(path))
        task = Task.from_meta(meta)
        # notes + VCL live in the body — pick them back up for round-trips
        section: Optional[str] = None      # None | "notes" | "vcl"
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("## Notes"):
                section = "notes"
                continue
            if stripped.startswith("## Version Control Log"):
                section = "vcl"
                continue
            if section and stripped.startswith("- "):
                (task.notes if section == "notes" else task.vcl).append(
                    stripped[2:])
        return task

    def list(self, goal_id: str, status: Optional[str] = None) -> list[Task]:
        folder = self._tasks_dir(goal_id)
        if not folder.exists():
            return []
        tasks = []
        for path in sorted(folder.glob("*.md")):
            meta, _ = self._parse(read_text(path))
            t = Task.from_meta(meta)
            if status is None or t.status == status:
                tasks.append(t)
        return tasks

    def _unique_id(self, goal_id: str, title: str) -> str:
        base = slugify(title, "task")
        existing = {t.task_id for t in self.list(goal_id)}
        cand, i = base, 2
        while cand in existing:
            cand = f"{base}-{i}"
            i += 1
        return cand
