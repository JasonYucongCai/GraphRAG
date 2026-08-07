"""
IPP_Social.integration — the strict IPP v0.2.8 platform assembly.

One shared GraphContext 𝒢 holds EVERY runtime peer:

    𝒢 = { llm, social_activity, <20× engine+tools nodes>, social_portal }

  1. the LLM node        — LLMs/ipp.json via Γ
  2. the social node     — IPP_Social/social_activity/ipp.json via Γ
  3. the 20 agents       — each ManyAgents/Codex_* gets its own finalized
                           engine/tools ipp.json (unique node ids) and its
                           engine + tools nodes constructed into 𝒢
  4. the portal node     — IPP_Social/portal/ipp.json via Γ; its swarm
                           channel's external topology resolves to the
                           engine nodes' chat_stream channels in 𝒢

Every runtime interaction then flows through the guardrail envelopes:
portal → social_activity (goals/tasks/board), portal → agent engine
nodes (chat_stream), agents → social_activity (task completion + board).

``build_platform`` is the single entry point used by ui/server.py.
"""
from __future__ import annotations

from typing import Any, Optional

from IPP_Social.portal.construct import create_portal_node
from IPP_Social.social_activity.construct import create_social_node
from IPP_Social.swarm.agent_ipp import (
    build_engine, construct_agent_nodes, finalize_all_agents,
    list_agent_folders,
)
from IPP_Social.swarm.bus import SwarmBus
from IPP_Social.swarm.runtime import AgentRuntime
from IPP_Social.swarm.swarm import SwarmManager


def build_platform(graph, encoder, provider, store=None,
                   agent_chat_mode: bool = True,
                   max_concurrent: int = 4,
                   bus: Optional[SwarmBus] = None) -> dict:
    """Assemble the complete Multi Agent platform (strict IPP v0.2.8).

    Returns the platform dict:
      ctx, llm_node, social_node, components, portal_node, swarm,
      runtimes (agent_id → AgentRuntime)
    """
    from ipp.IPP_registry import GraphContext
    from LLMs.IPP import llm_node
    from IPP_Social.settings import SettingsStore

    ctx = GraphContext()                       # the ONE shared graph context
    settings = SettingsStore()                 # platform settings (Settings tab)

    # 1) LLM node
    llm = llm_node(context=ctx)

    # 2) social_activity node (its own component modules, same 𝒢)
    social_node, components = create_social_node(context=ctx)

    # the human operator at the portal can post on the global chat board
    from IPP_Social.agents.agent_card import AgentCard
    ds = components["dataset"]
    if ds.load_card("user") is None:
        ds.save_card(AgentCard(agent_id="user", name="User",
                               bio="the human operator at the portal"))

    # 3) the 20 ManyAgents — finalize their IPP identity, build nodes
    finalize_all_agents()                      # idempotent
    runtimes: dict[str, AgentRuntime] = {}
    swarm_bus = bus or SwarmBus()
    for folder in list_agent_folders():
        agent_id = folder.name
        engine = build_engine(agent_id, graph, encoder, provider, store,
                              chat_mode=agent_chat_mode,
                              social_node=social_node)
        construct_agent_nodes(agent_id, engine, ctx,
                              chat_mode=agent_chat_mode)
        runtimes[agent_id] = AgentRuntime(agent_id, engine, swarm_bus,
                                          social_node, settings=settings)
    swarm = SwarmManager(list(runtimes.values()), social_node,
                         bus=swarm_bus, max_concurrent=max_concurrent,
                         settings=settings)
    swarm.apply_settings()

    # 4) the portal node — resolves its swarm topology against 𝒢
    portal_node = create_portal_node(ctx, swarm, social_node,
                                     settings=settings)

    # 5) the conversation loop — agents reply to inbox messages
    swarm.start_responder()

    return {
        "ctx": ctx,
        "llm_node": llm,
        "social_node": social_node,
        "components": components,
        "portal_node": portal_node,
        "swarm": swarm,
        "runtimes": runtimes,
    }


def verify_platform(platform: dict, sample_agents: int = 3) -> list[str]:
    """Verify 17 invariants on the portal, social and engine nodes.

    Returns a list of failures ([] = all verified).
    """
    from ipp.IPP_verify import verify_node

    failures: list[str] = []
    for node in (platform["portal_node"], platform["social_node"],
                 platform["llm_node"]):
        fails = verify_node(node)
        if fails:
            failures.append(f"{node.node_id}: {fails}")
    for agent_id, rt in list(platform["runtimes"].items())[:sample_agents]:
        fails = verify_node(rt.engine.node)
        if fails:
            failures.append(f"{agent_id} engine: {fails}")
        fails = verify_node(rt.engine._tools_node)
        if fails:
            failures.append(f"{agent_id} tools: {fails}")
    return failures
