"""
task_manager — the shared task management.

A **goal is a folder**; its **individual tasks are Markdown files**
inside it. Any agent may create goals, create tasks, and update
status/notes/assignee — collaboration toward making the goal true.
The actual goals live in the social database
(``social_database/goals/<goal_id>/``).
"""
from __future__ import annotations

from IPP_Social.task_manager.goals import (
    GOAL_STATUSES, Goal, GoalManager,
)
from IPP_Social.task_manager.manager import TaskManagement
from IPP_Social.task_manager.tasks import (
    TERMINAL_STATUSES, TASK_STATUSES, Task, TaskManager,
)

__all__ = [
    "GOAL_STATUSES", "Goal", "GoalManager",
    "TASK_STATUSES", "TERMINAL_STATUSES", "Task", "TaskManager",
    "TaskManagement",
]
