"""
task_manager.manager — the TaskManagement facade.

Combines GoalManager (goal folders) + TaskManager (task Markdown files)
into one object the IPP handlers use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from IPP_Social.IPP_Social_services_tools.IPP_Social_tasks_goals import Goal, GoalManager
from IPP_Social.IPP_Social_services_tools.IPP_Social_tasks_tasks import Task, TaskManager


class TaskManagement:
    """The shared goal/task collaboration facade."""

    def __init__(self, goals_root: Path | str | None = None):
        self.goals = GoalManager(goals_root)
        self.tasks = TaskManager(goals_root)

    # ── goals ────────────────────────────────────────────────────────────
    def create_goal(self, title: str, description: str = "",
                    owner_agent_id: str = "",
                    goal_id: str | None = None) -> Goal:
        return self.goals.create(title, description, owner_agent_id, goal_id)

    def list_goals(self) -> list[Goal]:
        return self.goals.list()

    def get_goal(self, goal_id: str) -> Goal:
        return self.goals.get(goal_id)

    def archive_goal(self, goal_id: str) -> Goal:
        return self.goals.archive(goal_id)

    def delete_goal(self, goal_id: str) -> None:
        """Permanently remove a goal folder and its task files."""
        return self.goals.delete(goal_id)

    # ── tasks ────────────────────────────────────────────────────────────
    def create_task(self, goal_id: str, title: str,
                    description: str = "",
                    assignee_agent_id: str = "",
                    task_id: str | None = None,
                    author_agent_id: str = "",
                    depends_on: list | None = None,
                    status: str = "submitted") -> Task:
        return self.tasks.create(goal_id, title, description,
                                 assignee_agent_id, task_id,
                                 author_agent_id, depends_on, status)

    def update_task(self, goal_id: str, task_id: str, agent_id: str,
                    status: Optional[str] = None,
                    note: Optional[str] = None,
                    assignee: Optional[str] = None) -> Task:
        return self.tasks.update(goal_id, task_id, agent_id,
                                 status=status, note=note, assignee=assignee)

    def get_task(self, goal_id: str, task_id: str) -> Task:
        return self.tasks.get(goal_id, task_id)

    def list_tasks(self, goal_id: str,
                   status: Optional[str] = None) -> list[Task]:
        return self.tasks.list(goal_id, status)
