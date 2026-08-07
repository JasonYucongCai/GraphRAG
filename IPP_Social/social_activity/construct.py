"""
social_activity.construct — the Constructor (Γ) of the social_activity node.

Γ ⊩ F × 𝒢 ↝ ((Ω_k, Ξ_k[τ*_k]), ℰ_int) for the six channels:
card, profile, tasks, chat_board, events, a2a.

The module facades (AgentDataset, TaskManagement, ChatBoard, EventBus,
PushNotifier, A2AContext) are built as ONE shared set over one social
database and bound into the GraphContext for the handler factories.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ipp.IPP_constructor import IPPConstructor
from ipp.IPP_registry import GraphContext

from IPP_Social.agents.dataset import AgentDataset
from IPP_Social.a2a.modes import A2AContext
from IPP_Social.a2a.push import PushNotifier
from IPP_Social.chat_board.board import ChatBoard
from IPP_Social.events.bus import EventBus
from IPP_Social.social_activity.IPP_executor import (
    SocialExecutor, SocialStreamExecutor,
)
from IPP_Social.task_manager.manager import TaskManagement

_IPP_JSON = Path(__file__).resolve().parent / "ipp.json"

DEFAULT_EXECUTOR_CLASSES: dict[str, type] = {
    "card": SocialExecutor,
    "profile": SocialExecutor,
    "tasks": SocialExecutor,
    "chat_board": SocialExecutor,
    "events": SocialStreamExecutor,
    "a2a": SocialExecutor,
}


def build_social_components(db_root: Optional[Path | str] = None,
                            dataset_root: Optional[Path | str] = None
                            ) -> dict:
    """One shared set of module instances over one social database.

    ``db_root``      — the social database folder (goals/, chat/,
                       events/, push/); defaults to
                       ``IPP_Social/social_database``.
    ``dataset_root`` — the agent-card dataset folder; defaults to
                       ``IPP_Social/agents/dataset``.
    """
    base = Path(db_root) if db_root else None
    dataset = AgentDataset(dataset_root)
    events = EventBus(root=(base / "events") if base else None)
    push = PushNotifier(root=(base / "push") if base else None,
                        event_bus=events)
    tasks = TaskManagement(goals_root=(base / "goals") if base else None)
    chat = ChatBoard(root=(base / "chat") if base else None,
                     dataset=dataset, event_bus=events, push=push)
    a2a_ctx = A2AContext(tasks=tasks, events=events, push=push,
                         dataset=dataset)
    return {"dataset": dataset, "tasks": tasks, "chat": chat,
            "events": events, "push": push, "a2a_ctx": a2a_ctx}


def create_social_node(db_root: Optional[Path | str] = None,
                       dataset_root: Optional[Path | str] = None,
                       context: Optional[GraphContext] = None,
                       register: bool = True,
                       components: Optional[dict] = None):
    """Γ ⊩ social_activity/ipp.json × 𝒢 ↝ the social IPP node.

    Returns ``(node, components)`` — components is the dict of shared
    module instances (dataset, tasks, chat, events, push, a2a_ctx).
    """
    ctx = context or GraphContext()
    comps = components or build_social_components(db_root, dataset_root)
    for key, value in comps.items():
        ctx.bind(key, value)
    gamma = IPPConstructor(ctx, executor_classes=dict(DEFAULT_EXECUTOR_CLASSES))
    node = gamma.construct_file(_IPP_JSON, ctx)
    gamma.recall_scope(node)
    if register:
        ctx.register_node(node)
    return node, comps
