"""
IPP_Social.integration — the strict IPP v0.2.8 platform assembly.

One shared GraphContext 𝒢 holds EVERY runtime peer:

    𝒢 = { llm, social_activity, database, tools, <20× engine+tools nodes>,
          social_portal }

  1. the LLM node        — LLMs/IPP.json via Γ
  2. the social node     — IPP_Social/social_activity/IPP.json via Γ
  3. the database node   — database/IPP.json via Γ (the note store as an
                           IPP component; one node per process, shared
                           with the tool facade and the web server)
  4. the tools node      — tools/IPP.json via Γ (the SHARED runtime: tool
                           dispatch + graph/encoder/build/check ops; the
                           per-agent tools nodes resolve their invoke
                           channel DOWNSTREAM to it — one execution
                           plane, one audit trail)
  5. the 20 agents       — each ManyAgents/Codex_* gets its own finalized
                           engine/tools IPP.json (unique node ids) and its
                           engine + tools nodes constructed into 𝒢
  6. the portal node     — IPP_Social/portal/IPP.json via Γ; its swarm
                           channel's external topology resolves to the
                           engine nodes' chat_stream channels in 𝒢

Every runtime interaction then flows through the guardrail envelopes:
portal → social_activity (goals/tasks/board), portal → agent engine
nodes (chat_stream), agents → social_activity (task completion + board),
ALL store mutations → database, and ALL tool executions → tools.

``build_platform`` is the single entry point used by ui/server.py.
"""
from __future__ import annotations

from typing import Any, Optional

from IPP_Social.IPP_Social_services_tools.IPP_Social_portal_tool_construct import create_portal_node
from IPP_Social.IPP_Social_services_tools.IPP_Social_services_construct import create_social_node
from ManyAgents.swarm.agent_ipp import (
    build_engine, construct_agent_nodes, finalize_all_agents,
    list_agent_folders,
)
from ManyAgents.swarm.bus import SwarmBus
from ManyAgents.swarm.runtime import AgentRuntime
from ManyAgents.swarm.swarm import SwarmManager


def build_platform(graph, encoder, provider, store=None,
                   agent_chat_mode: bool = True,
                   max_concurrent: int = 4,
                   bus: Optional[SwarmBus] = None) -> dict:
    """Assemble the complete Multi Agent platform (strict IPP v0.2.8).

    Returns the platform dict:
      ctx, llm_node, social_node, components, portal_node, swarm,
      runtimes (agent_id → AgentRuntime)
    """
    from IPP.IPP_registry import GraphContext
    from LLMs.IPP import llm_node
    from IPP_Social.settings import SettingsStore

    ctx = GraphContext()                       # the ONE shared graph context
    settings = SettingsStore()                 # platform settings (Settings tab)

    # 1) LLM node
    llm = llm_node(context=ctx)

    # 2) social_activity node (its own component modules, same 𝒢)
    social_node, components = create_social_node(context=ctx)

    # the human operator at the portal can post on the global chat board
    from ManyAgents.agent_management.agent_card import AgentCard
    ds = components["dataset"]
    if ds.load_card("user") is None:
        ds.save_card(AgentCard(agent_id="user", name="User",
                               bio="the human operator at the portal"))

    # provision the 20 ManyAgents into the social dataset so the chat
    # board, push notifier and A2A methods recognise them
    from IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision import provision_many_agents
    provision_many_agents(ds)

    # 3) the database node — the note store as an IPP component (one node
    # per process, shared with the tool facade + the web server). The
    # agents' database tools route to it through the tools node router.
    from database.construct import database_node
    db_node = database_node(store=store, graph=graph)
    ctx.register_node(db_node)

    # 4) the tools node — the SHARED runtime as an IPP component, built
    # BEFORE the agents so their tools nodes' invoke channel resolves its
    # downstream edge to tools.invoke (constructor-resolved in 𝒢).
    from general_tools.construct import bind_tools, tools_node
    bind_tools(graph=graph, encoder=encoder)
    tools = tools_node()
    ctx.register_node(tools)

    # 5) the 20 ManyAgents — finalize their IPP identity, build nodes
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

    # 6) the portal node — resolves its swarm topology against 𝒢
    portal_node = create_portal_node(ctx, swarm, social_node,
                                     settings=settings)

    # 7) the conversation loop — agents reply to inbox messages.
    # NOT auto-started: only activates when the user clicks "▶ Start Team"
    # in the Multi Agent portal. The responder is created but idle.

    # the tools node reads the agent registry + the social node LIVE
    # (routing: the social_* tools route to social_activity's channels) —
    # bind them now that every runtime exists (no re-construction needed)
    bind_tools(agents={agent_id: rt.engine
                       for agent_id, rt in runtimes.items()},
               social_node=social_node)

    return {
        "ctx": ctx,
        "llm_node": llm,
        "social_node": social_node,
        "database_node": db_node,
        "tools_node": tools,
        "components": components,
        "portal_node": portal_node,
        "swarm": swarm,
        "runtimes": runtimes,
        "settings": settings,
    }


def verify_platform(platform: dict, sample_agents: int = 3) -> list[str]:
    """Verify 17 invariants on the portal, social, llm, database, tools
    and engine nodes.

    Returns a list of failures ([] = all verified).
    """
    from IPP.IPP_verify import verify_node

    failures: list[str] = []
    for node in (platform["portal_node"], platform["social_node"],
                 platform["llm_node"], platform["database_node"],
                 platform["tools_node"]):
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
