"""
portal.construct — the Constructor (Γ) of the social_portal node.

Γ ⊩ social_portal/ipp.json × 𝒢 ↝ the portal IPP node with four channels
(discover, command, monitor, swarm). External topology is resolved
against the shared GraphContext 𝒢 (social_activity node + 20 engine
nodes), and the swarm channel's resolved downstream is handed to the
SwarmManager (τ*_k enforcement at start time).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ipp.IPP_constructor import IPPConstructor
from ipp.IPP_registry import GraphContext

from IPP_Social.portal.IPP_executor import PortalExecutor

_IPP_JSON = Path(__file__).resolve().parent / "ipp.json"

DEFAULT_EXECUTOR_CLASSES: dict[str, type] = {
    "discover": PortalExecutor,
    "command": PortalExecutor,
    "monitor": PortalExecutor,
    "swarm": PortalExecutor,
    "settings": PortalExecutor,
}


def create_portal_node(context: GraphContext, swarm, social_node,
                       settings=None,
                       register: bool = True,
                       executor_classes: Optional[dict] = None):
    """Γ ⊩ social_portal/ipp.json × 𝒢 ↝ the portal IPP node.

    Binds the shared context, the swarm manager, the social node and the
    settings store for the handler factories; resolves external topology
    against 𝒢 and hands the swarm channel's resolved downstream (the
    agent engine targets) to the SwarmManager.
    """
    context.bind("ctx", context)
    context.bind("swarm", swarm)
    context.bind("social_node", social_node)
    if settings is not None:
        context.bind("settings", settings)
    gamma = IPPConstructor(context, executor_classes=executor_classes
                           or DEFAULT_EXECUTOR_CLASSES)
    node = gamma.construct_file(_IPP_JSON, context)
    gamma.recall_scope(node)
    if register:
        context.register_node(node)
    # τ*_k → the swarm manager (strict external-topology enforcement)
    swarm.attach_topology(node.executors["swarm"].downstream)
    return node
