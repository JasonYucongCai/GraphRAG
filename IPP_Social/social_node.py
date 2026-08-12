"""
IPP_Social.social_node — Γ construction of the social IPP node.

The canonical way to construct the social node, same pattern as LLMs/IPP.py:

    from IPP_Social.social_node import social_node, build_components

    comps = build_components()
    node = social_node(comps, swarm=swarm_mgr, settings=settings_store)
    result = node.invoke("card", {"op": "list"})

Γ reads IPP_Social/IPP.json, binds the components + swarm + settings into
the GraphContext, and returns the assembled IPPNode with all 11 channels
guarded by SocialExecutor (Ξ).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from IPP.IPP_constructor import IPPConstructor
from IPP.IPP_registry import GraphContext

from IPP_Social.IPP_executor import SocialExecutor
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_modes import A2AContext
from IPP_Social.IPP_Social_communication_tools.IPP_Social_a2a_push import PushNotifier
from IPP_Social.IPP_Social_communication_tools.IPP_Social_chatboard_tool import ChatBoard
from IPP_Social.IPP_Social_services_tools.IPP_Social_event_tool_bus import EventBus
from IPP_Social.IPP_Social_services_tools.IPP_Social_tasks_manager import TaskManagement
from ManyAgents.agent_management.dataset import AgentDataset

_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"

CHANNELS = ["card", "profile", "tasks", "chat_board", "events", "a2a",
            "discover", "command", "monitor", "swarm", "settings"]


def build_components(db_root=None, dataset_root=None) -> dict:
    """Build the shared module instances over one social database.

    Returns {dataset, tasks, chat, events, push, a2a_ctx} — the six
    facades that IPP_Social/IPP_object.py handlers resolve from bindings.
    """
    base = Path(db_root) if db_root else None
    dataset = AgentDataset(dataset_root)
    events = EventBus(root=(base / "events") if base else None)
    push = PushNotifier(root=(base / "push") if base else None, event_bus=events)
    tasks = TaskManagement(goals_root=(base / "goals") if base else None)
    chat = ChatBoard(root=(base / "chat") if base else None, dataset=dataset,
                     event_bus=events, push=push)
    a2a_ctx = A2AContext(tasks=tasks, events=events, push=push, dataset=dataset)
    return {"dataset": dataset, "tasks": tasks, "chat": chat,
            "events": events, "push": push, "a2a_ctx": a2a_ctx}


def social_node(components: dict, swarm: Any = None, settings: Any = None,
                context: Optional[GraphContext] = None,
                register: bool = True):
    """Γ ⊩ IPP_Social/IPP.json × 𝒢 ↝ the social IPP node (11 channels).

    Args:
        components: dict from build_components()
        swarm: the SwarmManager (bound as bindings["swarm"])
        settings: the SettingsStore (bound as bindings["settings"])
        context: GraphContext 𝒢 (fresh if omitted)
        register: register the node into 𝒢

    Returns:
        The assembled IPPNode with all 11 channels guarded by SocialExecutor.
    """
    ctx = context or GraphContext()
    for key, value in components.items():
        ctx.bind(key, value)
    if swarm is not None:
        ctx.bind("swarm", swarm)
    if settings is not None:
        ctx.bind("settings", settings)

    gamma = IPPConstructor(ctx, executor_classes={ch: SocialExecutor for ch in CHANNELS})
    node = gamma.construct_file(_IPP_JSON, ctx)
    if register:
        ctx.register_node(node)
    return node
