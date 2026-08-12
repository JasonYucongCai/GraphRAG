"""
IPP_Social.platform — the Multi Agent platform assembly entry point.

IPP_Social is an independent module: it brings together ManyAgents (the
20 agent instances + swarm runtime), the social IPP node (11 channels),
the database node, the tools node, and the LLM node into one running
platform. Callers (ui/server.py, integration_demo.py, CLI tools) import
and call build_platform() — the server contains NO platform logic.

    from IPP_Social.platform import build_platform

    platform = build_platform(graph, encoder, llm_node=llm)
    platform["social_node"].invoke("discover", {"op": "agents"})
"""
from __future__ import annotations

from typing import Optional

from IPP.IPP_registry import GraphContext

from IPP_Social.social_node import build_components, social_node
from IPP_Social.settings import SettingsStore


def build_platform(graph, encoder, llm_node=None, store=None,
                   agent_chat_mode: bool = True,
                   max_concurrent: int = 4,
                   bus=None) -> dict:
    """Assemble the complete Multi Agent platform.

    Wires together: LLM node → 20 ManyAgents → SwarmManager →
    SocialResponder → Social IPP node → Database node → Tools node.
    Returns {ctx, llm_node, social_node, database_node, tools_node,
             components, swarm, runtimes, settings}.
    """
    from ManyAgents.swarm.agent_ipp import (
        build_engine, construct_agent_nodes, finalize_all_agents,
        list_agent_folders,
    )
    from ManyAgents.swarm.bus import SwarmBus
    from ManyAgents.swarm.runtime import AgentRuntime
    from ManyAgents.swarm.swarm import SwarmManager
    from ManyAgents.swarm.responder import SocialResponder
    from ManyAgents.agent_management.agent_card import AgentCard
    from LLMs import llm_node as _llm_node
    from IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision import provision_many_agents
    from database.construct import database_node
    from general_tools.construct import bind_tools, tools_node

    ctx = GraphContext()
    settings = SettingsStore()

    # 1) LLM node
    llm = llm_node or _llm_node()
    ctx.register_node(llm)

    # 2) Social components (dataset, tasks, chat, events, push, a2a)
    components = build_components()
    ds = components["dataset"]
    if ds.load_card("user") is None:
        ds.save_card(AgentCard(agent_id="user", name="User",
                               bio="the human operator at the portal"))
    provision_many_agents(ds)

    # 3) Database + tools
    db_node = database_node(store=store, graph=graph)
    ctx.register_node(db_node)
    bind_tools(graph=graph, encoder=encoder)
    tools = tools_node()
    ctx.register_node(tools)

    # 4) 20 agents + swarm
    finalize_all_agents()
    runtimes: dict[str, AgentRuntime] = {}
    swarm_bus = bus or SwarmBus()

    for folder in list_agent_folders():
        agent_id = folder.name
        engine = build_engine(agent_id, graph, encoder, llm_node=llm, store=store,
                              chat_mode=agent_chat_mode, social_node=None)
        construct_agent_nodes(agent_id, engine, ctx, chat_mode=agent_chat_mode)
        runtimes[agent_id] = AgentRuntime(agent_id, engine, swarm_bus,
                                          None, settings=settings)

    swarm = SwarmManager(list(runtimes.values()), None,
                         bus=swarm_bus, max_concurrent=max_concurrent,
                         settings=settings)
    swarm.apply_settings()

    # 5) Social IPP node — Γ ⊩ IPP_Social/IPP.json × 𝒢
    social = social_node(components, swarm=swarm, settings=settings,
                         context=ctx, register=True)
    swarm.attach_topology(social.executors["swarm"].downstream)

    for rt in runtimes.values():
        rt.social_node = social
    swarm.social_node = social
    swarm.responder = SocialResponder(swarm, settings, social_node=social)
    bind_tools(agents={aid: rt.engine for aid, rt in runtimes.items()},
               social_node=social)

    return {
        "ctx": ctx, "llm_node": llm, "social_node": social,
        "portal_node": social,   # backward compat: portal channels are in social node
        "database_node": db_node, "tools_node": tools,
        "components": components, "swarm": swarm,
        "runtimes": runtimes, "settings": settings,
    }


def verify_platform(platform: dict, sample_agents: int = 3) -> list[str]:
    """Verify 17 invariants on all platform nodes. Returns list of failures."""
    from IPP.IPP_verify import verify_node
    failures: list[str] = []
    for key in ("social_node", "llm_node", "database_node", "tools_node"):
        node = platform.get(key)
        if node:
            fails = verify_node(node)
            if fails:
                failures.append(f"{node.node_id}: {fails}")
    for agent_id, rt in list(platform["runtimes"].items())[:sample_agents]:
        if rt.engine.node:
            fails = verify_node(rt.engine.node)
            if fails:
                failures.append(f"{agent_id} engine: {fails}")
        if rt.engine._tools_node:
            fails = verify_node(rt.engine._tools_node)
            if fails:
                failures.append(f"{agent_id} tools: {fails}")
    return failures
