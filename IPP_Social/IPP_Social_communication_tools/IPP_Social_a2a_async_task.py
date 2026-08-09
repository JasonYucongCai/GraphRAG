"""
a2a.async_task — formal method #2: AsyncTask (asynchronous).

Task-based interaction: submit a task into a goal folder, then poll it
for updates; each poll responds with the task's current status.

  action = "submit"  → create (or update) a task; returns a poll handle
  action = "status"  → respond with the task's current status
"""
from __future__ import annotations

from typing import Optional

from IPP_Social.errors import SocialError
from IPP_Social.IPP_Social_services_tools.IPP_Social_tasks_manager import TaskManagement
from IPP_Social.util import now_iso


class AsyncTask:
    """The asynchronous task-based A2A method."""

    name = "AsyncTask"

    def __init__(self, tasks: Optional[TaskManagement] = None):
        self.tasks = tasks or TaskManagement()

    # ── submit ───────────────────────────────────────────────────────────
    def submit(self, from_agent_id: str, goal_id: str, message: str,
               title: str = "handoff", to_agent_id: str = "",
               task_id: Optional[str] = None) -> dict:
        goal = self.tasks.get_goal(goal_id)          # UnknownGoal if missing
        existing = (self.tasks.get_task(goal_id, task_id)
                    if task_id else None)
        if existing is not None:
            # update path: the collaboration continues on an existing task
            task = self.tasks.update_task(
                goal_id, task_id, from_agent_id,
                status=None, note=message, assignee=to_agent_id or None)
            return {
                "ok": True, "mode": "async", "action": "submit",
                "task_id": task.task_id, "goal_id": goal.goal_id,
                "status": task.status,
                "poll": {"channel": "tasks", "op": "get_task",
                         "goal_id": goal.goal_id, "task_id": task.task_id},
                "response": f"task {task.task_id} updated → {task.status}",
            }
        task = self.tasks.create_task(
            goal_id=goal_id, title=title,
            description=message,
            assignee_agent_id=to_agent_id,
            task_id=task_id,
            author_agent_id=from_agent_id,
            status="processing")
        task.vcl.append(f"{now_iso()}: submitted via a2a async by "
                        f"{from_agent_id}")
        self.tasks.tasks.save(task)
        return {
            "ok": True, "mode": "async", "action": "submit",
            "task_id": task.task_id, "goal_id": goal.goal_id,
            "status": task.status,
            "poll": {"channel": "tasks", "op": "get_task",
                     "goal_id": goal.goal_id, "task_id": task.task_id},
            "response": f"task {task.task_id} submitted ({task.status})",
        }

    # ── status (the poll) ────────────────────────────────────────────────
    def status(self, from_agent_id: str, goal_id: str,
               task_id: str) -> dict:
        task = self.tasks.get_task(goal_id, task_id)   # UnknownTask if missing
        return {
            "ok": True, "mode": "async", "action": "status",
            "task_id": task.task_id, "goal_id": task.goal_id,
            "status": task.status,
            "assignee_agent_id": task.assignee_agent_id,
            "updated": task.updated,
            "response": f"task {task.task_id} is {task.status}",
        }
