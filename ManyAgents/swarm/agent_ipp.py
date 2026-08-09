"""
swarm.agent_ipp — per-agent IPP v0.2.8 identity + construction.

The 20 ManyAgents copies were cloned from codex_normal, so their
engine/tools ``IPP.json`` files still declare node_id
``codex_normal_engine`` / ``codex_normal_tools`` and bind handlers from
``codex_normal.*``. For the Multi Agent portal to connect every agent
STRICTLY as its own IPP node, each copy is finalized:

  • node_id           ``Codex_XX_Name_engine`` / ``Codex_XX_Name_tools``
  • handler refs      ``ManyAgents.Codex_XX_Name.engine.IPP_object:...``
  • chat_stream       → the live streaming handler (swarm.IPP_object)
  • log endpoints     ``graph_data/logs/IPP/<node_id>.<channel>.jsonl``
  • fallback refs     per-agent

``construct_agent_nodes`` then builds the agent's tools + engine nodes
through Γ into a SHARED GraphContext 𝒢 (one registry for all 20 agents,
the LLM node and the social node) — every handler factory captures its
own engine because bindings are snapshotted at construction time.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Optional

from IPP.IPP_constructor import IPPConstructor
from IPP.IPP_registry import GraphContext
from general_tools.agent_specs import tool_set

MANY_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "ManyAgents"

# the live-streaming handler bound into every agent's chat_stream channel
LIVE_CHAT_STREAM_HANDLER = "ManyAgents.swarm.IPP_object:make_live_chat_stream_handler"


def list_agent_folders(root: Optional[Path | str] = None) -> list[Path]:
    """The 20 Codex agent folders (excludes codex_normal/codex copy)."""
    base = Path(root) if root else MANY_AGENTS_ROOT
    return sorted(p for p in base.glob("Codex_[0-9]*") if p.is_dir())


def finalize_agent_ipp(agent_folder: Path, force: bool = False) -> str:
    """Rewrite one agent's engine/ + general_tools/ IPP.json with its own identity.

    Idempotent: skips when the files already carry the agent's node_id
    (unless ``force``). Returns the agent_id (folder name).
    """
    agent_id = agent_folder.name
    for sub in ("engine", "tools"):
        path = agent_folder / sub / "IPP.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        new_node = f"{agent_id}_{sub}"
        if raw.get("node_id") == new_node and not force:
            continue
        raw["node_id"] = new_node
        for ch in raw.get("channels", []):
            handler = ch.get("handler", "")
            if handler.startswith("codex_normal.engine.IPP_object"):
                ch["handler"] = handler.replace(
                    "codex_normal.engine.IPP_object",
                    f"ManyAgents.{agent_id}.engine.IPP_object")
            elif handler.startswith("codex_normal.tools.IPP_object"):
                ch["handler"] = handler.replace(
                    "codex_normal.tools.IPP_object",
                    f"ManyAgents.{agent_id}.tools.IPP_object")
            if sub == "engine" and ch.get("channel_id") == "chat_stream":
                ch["handler"] = LIVE_CHAT_STREAM_HANDLER
            ex = ch.get("ipp_executor", {})
            prov = ex.get("provenance", {})
            endpoint = prov.get("log_endpoint", "")
            if "codex_normal_engine" in endpoint or \
                    "codex_normal_tools" in endpoint:
                prov["log_endpoint"] = endpoint.replace(
                    "codex_normal_engine", f"{agent_id}_engine").replace(
                    "codex_normal_tools", f"{agent_id}_tools")
            fb = ex.get("error_handling", {}).get("fallback_nodes", [])
            ex.setdefault("error_handling", {})["fallback_nodes"] = [
                f.replace("codex_normal_engine", f"{agent_id}_engine")
                for f in fb]
        path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return agent_id


def finalize_all_agents(force: bool = False) -> list[str]:
    """Finalize all 20 agent folders; returns the agent ids."""
    return [finalize_agent_ipp(folder, force=force)
            for folder in list_agent_folders()]


def construct_agent_nodes(agent_id: str, engine, ctx: GraphContext,
                          chat_mode: bool = True,
                          register: bool = True):
    """Γ ⊩ <agent>/engine|tools/IPP.json × 𝒢 ↝ the agent's two IPP nodes.

    Binds this agent's engine/tool_names/agent_id right before each
    construction so every handler factory closes over the right engine
    (bindings are snapshotted per constructor call).

    Returns (engine_node, tools_node).
    """
    folder = MANY_AGENTS_ROOT / agent_id
    # the full general-purpose suite — SOCIAL TOOLS FIRST (the agent sees
    # them at the top of its tool list: chat, cards, goals)
    base_tools = tool_set("codex_normal")
    tool_names = [t for t in base_tools if t.startswith("social_")] + \
                 [t for t in base_tools if not t.startswith("social_")]
    # engine node — executor classes from the agent's own module
    exec_mod = importlib.import_module(
        f"ManyAgents.{agent_id}.engine.IPP_executor")
    AgentExecutor = exec_mod.AgentExecutor
    ctx.bind("engine", engine)
    ctx.bind("tool_names", tool_names)
    ctx.bind("agent_id", agent_id)
    gamma = IPPConstructor(ctx, executor_classes={
        "ground": AgentExecutor, "chat": AgentExecutor,
        "chat_stream": AgentExecutor})
    engine_node = gamma.construct_file(folder / "engine" / "IPP.json", ctx)
    gamma.recall_scope(engine_node)
    # tools node — executor classes from the agent's own module
    tool_exec_mod = importlib.import_module(
        f"ManyAgents.{agent_id}.tools.IPP_executor")
    ToolExecutor = tool_exec_mod.ToolExecutor
    ctx.bind("engine", engine)
    ctx.bind("tool_names", tool_names)
    ctx.bind("agent_id", agent_id)
    gamma_t = IPPConstructor(ctx, executor_classes={
        "invoke": ToolExecutor, "list": ToolExecutor,
        "describe": ToolExecutor})
    tools_node = gamma_t.construct_file(folder / "tools" / "IPP.json", ctx)
    gamma_t.recall_scope(tools_node)
    if register:
        ctx.register_node(engine_node)
        ctx.register_node(tools_node)
    engine.node = engine_node
    engine._tools_node = tools_node
    engine._ipp_context = ctx
    return engine_node, tools_node


def build_engine(agent_id: str, graph, encoder, provider, store=None,
                 chat_mode: bool = True, social_node=None):
    """Instantiate the agent's engine class with its personality prompt.

    ``social_node`` is the social_activity IPP node — bound as
    ``engine._social_node`` so the agent's social tools reach the social
    layer by default; the system prompt is extended with the social
    instructions (discovery).
    """
    module = importlib.import_module(f"ManyAgents.{agent_id}.engine")
    engine = module.CodexNormalEngine(graph, encoder, llm=provider,
                                      store=store, chat_mode=chat_mode)
    engine.name = agent_id
    engine.agent_id = agent_id
    engine._social_node = social_node
    prompt_file = MANY_AGENTS_ROOT / agent_id / "system_prompt.md"
    if prompt_file.exists():
        engine.system_prompt = prompt_file.read_text(encoding="utf-8")
    engine.system_prompt += SOCIAL_PROMPT_APPENDIX
    return engine


SOCIAL_PROMPT_APPENDIX = """

## Social layer (IPP_Social)
You are part of a social network of agents connected through IPP.
Use the social_* tools to collaborate:
- social_post: post to the global chat board. to_agent_id='chat_board'
  broadcasts; to_agent_id='agents' addresses every agent;
  to_agent_id='<agent_id>' sends a direct inter-agent message
  (e.g. to_agent_id='Codex_01_Alice'). Your own agent_id will be
  injected automatically as author_agent_id — you do not need to
  provide it.
- social_board: read the global chat board (addressed messages from all
  agents, formatted with timestamps and sender → target labels).
- social_inbox: read your PERSONAL inbox — direct messages addressed to
  you and broadcasts you haven't seen yet. Use this FIRST when someone
  may have messaged you directly.
- social_agents: list all registered agents (ids and names).
- social_create_goal / social_create_task / social_update_task /
  social_get_task / social_goals: the shared goal folders — collaborate
  on tasks toward the goal (every task is a Markdown file with a VCL).
Be sociable: introduce yourself, answer your peers, and report progress
back to the team on the chat board."""
