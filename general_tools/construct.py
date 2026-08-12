"""
tools.construct — the Constructor (Γ) of the tools node + the shared-process
bridge.

Γ ⊩ tools/IPP.json × 𝒢 ↝ the SHARED runtime node with 26 channels
(invoke, list, describe, graph, encoder, build, check + the 19 codex
channels). The node is the SINGLE IPP surface of the shared tool layer:
the engine's dispatch (tools.api.execute_tool), the per-agent tools
nodes and the web server all invoke it through the guardrail envelopes,
and the tool DEFINITIONS the LLM sees are derived from the F-file
catalogs (tools/catalog.py) — there is no legacy BaseTool layer.

The shared bridge:

    bind_tools(graph, encoder, agents, social_node)  — (re)bind process-wide
    tools_node()                    — the singleton node (lazy construct)
    current_graph() / current_encoder() / current_agents()
    current_catalog()               — the F-file-derived tool catalog
    current_social_node()           — the platform's social node (routing)

One node per process: the server binds its graph/encoder at startup, the
platform registers the SAME node into its shared GraphContext 𝒢 (the
45th node), and the per-agent tools nodes (codex_* / ManyAgents) resolve
their invoke channel DOWNSTREAM to this node's invoke channel.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from IPP.IPP_constructor import IPPConstructor, IPPNode
from IPP.IPP_registry import GraphContext

logger = logging.getLogger("general_tools.construct")

_IPP_JSON = Path(__file__).resolve().parent / "IPP.json"

# ── the shared bridge (process-wide) ───────────────────────────────────────
_lock = threading.RLock()
_GRAPH = None
_ENCODER = None
_AGENTS: dict = {}
_SOCIAL_NODE = None
_CATALOG: dict = {}
_NODE: Optional[IPPNode] = None
_CTX: Optional[GraphContext] = None

# ── remote backend (multi-process architecture) ──────────────────────────
_remote_backend_url: str | None = None
_remote_local_keys: set[str] = set()


def set_remote_backend(url: str, local_keys: set[str] | None = None) -> None:
    """Configure this process to forward non-local tool calls to a remote
    Control Center via HTTP.

    Args:
        url:  e.g. ``"http://127.0.0.3:8000"``
        local_keys: set of ``node_key`` values that execute LOCALLY
                     (e.g. ``{"social_activity"}`` for Multi Agent mode).
                     When None or empty, ALL tools go remote.
    """
    global _remote_backend_url, _remote_local_keys
    with _lock:
        _remote_backend_url = url
        _remote_local_keys = set(local_keys or [])


def bind_tools(graph=None, encoder=None, agents=None,
               social_node=None) -> None:
    """(Re)bind the process-wide KnowledgeGraph / EncoderLayer / agent
    lookup / social node the tools node operates on. Handlers resolve the
    bindings LIVE on every call, so rebinds (server startup,
    /api/graph/rebuild, platform assembly) are honored without
    re-construction (I1)."""
    global _GRAPH, _ENCODER, _AGENTS, _SOCIAL_NODE
    with _lock:
        if graph is not None:
            _GRAPH = graph
        if encoder is not None:
            _ENCODER = encoder
        if agents is not None:
            _AGENTS = dict(agents)
        if social_node is not None:
            _SOCIAL_NODE = social_node


def current_graph():
    """Return the KnowledgeGraph bound to the tools node.
    Handlers read this LIVE at call time so rebinds (server rebuild,
    platform assembly) are honored without re-construction."""

    return _GRAPH


def current_encoder():
    """Return the EncoderLayer bound to the tools node (live read)."""

    return _ENCODER


def current_agents() -> dict:
    return _AGENTS


def current_social_node():
    return _SOCIAL_NODE


def current_catalog() -> dict:
    return _CATALOG


def reset_tools_node() -> None:
    """Drop the singleton node (tests / full platform rebuilds)."""
    global _NODE, _CTX, _GRAPH, _ENCODER, _AGENTS, _SOCIAL_NODE, _CATALOG
    with _lock:
        _NODE, _CTX, _GRAPH, _ENCODER = None, None, None, None
        _AGENTS, _SOCIAL_NODE, _CATALOG = {}, None, {}


# ══════════════════════════════════════════════════════════════════════════
# Γ — construction (7-step protocol via IPP.IPP_constructor)
# ══════════════════════════════════════════════════════════════════════════
def create_tools_node(context: Optional[GraphContext] = None,
                      graph=None, encoder=None, agents=None,
                      social_node=None, register: bool = True) -> IPPNode:
    """Γ ⊩ tools/IPP.json × 𝒢 ↝ the tools IPP node (26 channels).

    Step 5/6: the tool CATALOG (the LLM definitions, derived from the
    F-file channel schemas) is built and bound here — one declarative
    source, no parallel tool layer.
    """
    from general_tools.IPP_executor import ToolsExecutor
    from general_tools.catalog import build_catalog

    ctx = context or GraphContext()
    if (graph is not None or encoder is not None or agents is not None
            or social_node is not None):
        bind_tools(graph=graph, encoder=encoder, agents=agents,
                   social_node=social_node)
    global _CATALOG
    with _lock:
        _CATALOG = build_catalog()
    ctx.bind("tools_graph", current_graph())
    ctx.bind("tools_encoder", current_encoder())
    ctx.bind("tools_agents", current_agents())
    ctx.bind("tools_social_node", current_social_node())
    ctx.bind("tools_catalog", _CATALOG)
    executor_channels = ("invoke", "list", "describe", "graph", "encoder",
                         "build", "check")
    gamma = IPPConstructor(ctx, executor_classes={
        ch: ToolsExecutor for ch in executor_channels})
    node = gamma.construct_file(_IPP_JSON, ctx)
    gamma.recall_scope(node)
    if register:
        ctx.register_node(node)
    return node


def tools_node(graph=None, encoder=None, agents=None,
               social_node=None) -> IPPNode:
    """The process-wide singleton tools node (lazy construction).

    First call constructs the node with the current shared bindings;
    later calls return the same instance — one node, one audit trail,
    registered by the platform into its shared GraphContext 𝒢.
    """
    global _NODE, _CTX
    with _lock:
        if (graph is not None or encoder is not None or agents is not None
                or social_node is not None):
            bind_tools(graph=graph, encoder=encoder, agents=agents,
                       social_node=social_node)
        if _NODE is None:
            _CTX = GraphContext()
            _NODE = create_tools_node(context=_CTX, register=True)
            logger.info("tools IPP node constructed: %s (%d channels, "
                        "%d catalog entries)", _NODE.node_id,
                        len(_NODE.channels), len(_CATALOG))
        return _NODE


# ══════════════════════════════════════════════════════════════════════════
# invoke — the ROUTER (R*_k): tool name → the target channel's envelope
# ══════════════════════════════════════════════════════════════════════════

def _remote_invoke(node_key: str, channel: str, op: str | None,
                   payload: dict) -> dict:
    """Forward a tool call to the remote Control Center via HTTP.

    Sends {node_key, channel, payload} to the Control Center's internal
    API where the call is reconstructed against the real singletons.
    """
    import json, urllib.request, urllib.error
    # Merge the operation into the payload (matching the local path where
    # _target_node("self", channel, op, payload) does invoke({op: op, **payload}))
    remote_payload = dict(payload)
    if op is not None:
        remote_payload = {"op": op, **remote_payload}
    body = json.dumps({
        "node_key": node_key,
        "channel": channel,
        "payload": remote_payload,
    }, ensure_ascii=False, default=str).encode("utf-8")
    url = f"{_remote_backend_url}/api/internal/invoke"
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": "remote_unreachable",
                "content": f"[ERROR] Control Center unreachable: {exc}",
                "metadata": {}}


def _target_node(node_key: str, channel: str, op: str | None,
                 payload: dict):
    """Resolve the route target and invoke it. Returns the payload dict.

    - "self"           → a tools-node channel (its OWN envelope)
    - "database"       → the database node (process singleton)
    - "social_activity"→ the social node (bound by the platform)

    When a remote backend is configured (multi-process architecture),
    targets whose node_key is NOT in the local set are forwarded to
    the Control Center via HTTP.
    """
    # ── remote routing (multi-process) ─────────────────────────────────
    if _remote_backend_url and node_key not in _remote_local_keys:
        return _remote_invoke(node_key, channel, op, payload)

    if node_key == "self":
        ex = tools_node().executors[channel]
        if op is None:
            return ex.invoke(payload).payload
        return ex.invoke({"op": op, **payload}).payload
    if node_key == "database":
        from database.construct import database_node
        out = database_node().invoke(channel, {"op": op, **payload})
        return out.payload
    if node_key == "social_activity":
        node = current_social_node()
        if node is None:
            return {"ok": False, "error": "not_connected",
                    "message": "social layer not connected — run inside the "
                               "Multi Agent platform"}
        out = node.invoke(channel, {"op": op, **payload})
        return out.payload
    return {"ok": False, "error": "bad_route",
            "message": f"unknown route target {node_key!r}"}


def impl_execute_tool(args: dict) -> dict:
    """{tool, args, agent_id?, session_id?, workspace_root?, graph?} →
    {ok, content, error, metadata} — route one tool call to the target
    channel's guardrail envelope (both hops audited)."""
    from general_tools.routes import ROUTES
    from general_tools.catalog import definition

    name = str(args.get("tool", ""))
    tool_args = dict(args.get("args") or {})
    route = ROUTES.get(name)
    if route is None:
        return {"ok": False,
                "content": f"[ERROR] Unknown tool: {name!r}",
                "error": "unknown_tool", "metadata": {}}
    node_key, channel, op, adapter = route

    meta = {"agent_id": args.get("agent_id") or "",
            "session_id": args.get("session_id") or "",
            "workspace_root": args.get("workspace_root") or ""}
    payload = dict(tool_args)
    if adapter is not None:
        payload = adapter(tool_args, meta)
    # per-agent graph/encoder instances ride through the envelope (the
    # target impls prefer them over the process-wide bridge bindings)
    for key in ("graph", "encoder"):
        if args.get(key) is not None:
            payload[key] = args[key]

    out = _target_node(node_key, channel, op, payload)
    if not isinstance(out, dict):
        return {"ok": True, "content": str(out), "error": None,
                "metadata": {}}
    if out.get("ok"):
        extras = {k: v for k, v in out.items()
                  if k not in ("ok", "message", "content", "error", "text")}
        # prefer:  text (pre-formatted) > content > message > serialize
        content = (out.get("text")
                   or out.get("content")
                   or out.get("message")
                   or _serialize_social_result(out))
        return {"ok": True,
                "content": str(content),
                "error": None, "metadata": extras}
    return {"ok": False,
            "content": str(out.get("message") or out.get("content")
                           or out.get("error") or "operation failed"),
            "error": out.get("error"), "metadata": {}}


def _serialize_social_result(out: dict) -> str:
    """Turn a social_activity / database result into readable text for the LLM."""
    # messages (chat board)
    if "messages" in out:
        msgs = out["messages"]
        if not msgs:
            return "(board is empty)"
        if not isinstance(msgs, list):
            msgs = [msgs]
        # separate human operator posts — they go FIRST so the LLM can't miss them
        user_msgs = [m for m in msgs if isinstance(m, dict)
                     and m.get("author_agent_id") == "user"]
        agent_msgs = [m for m in msgs if isinstance(m, dict)
                      and m.get("author_agent_id") != "user"]
        lines = ["🌐 GLOBAL CHAT BOARD", ""]
        # ── USER MESSAGES FIRST ──────────────────────────
        if user_msgs:
            lines.append("📌 MESSAGES FROM THE HUMAN OPERATOR (read these FIRST!)")
            lines.append("─" * 50)
            for m in user_msgs[-15:]:  # last 15 user posts
                ts = (m.get("ts", "") or "")[11:19] if m.get("ts") else "??:??"
                to = m.get("to_agent_id", "")
                target = f" → {to}" if to and to not in ("chat_board",) else ""
                text = (m.get("text", "") or "")[:200]
                lines.append(f"  [{ts}] 👤 USER{target}: {text}")
        # ── RECENT BOARD ACTIVITY ────────────────────────
        recent = (agent_msgs + user_msgs)[-60:]  # last 60 overall, mixed
        recent.sort(key=lambda m: m.get("ts", ""))
        lines.append("")
        lines.append("📋 RECENT BOARD (most recent messages)")
        lines.append("─" * 50)
        for m in recent:
            author = m.get("author_agent_id", "?")
            to = m.get("to_agent_id", "")
            if to and to not in ("chat_board",):
                target = to
            else:
                target = "board"
            ts = (m.get("ts", "") or "")[11:19] if m.get("ts") else "??:??"
            text = (m.get("text", "") or "")[:100]
            tags = " ".join(f"#{t}" for t in (m.get("tags") or []))
            if author == "user":
                prefix = "👤 USER"
            else:
                prefix = author
            lines.append(f"[{ts}] {prefix} → {target}: {text} {tags}".rstrip())
        return "\n".join(lines)
    # cards (agent list)
    if "cards" in out:
        cards = out["cards"]
        if not cards:
            return "(no agents registered)"
        lines = ["👥 REGISTERED AGENTS", "─" * 50]
        for c in (cards if isinstance(cards, list) else [cards]):
            if isinstance(c, dict):
                lines.append(f"  {c.get('agent_id','?')}: {c.get('name','?')}")
        return "\n".join(lines)
    # goals
    if "goals" in out:
        goals = out["goals"]
        if not goals:
            return "(no goals)"
        lines = ["🎯 GOALS"]
        for g in (goals if isinstance(goals, list) else [goals]):
            if isinstance(g, dict):
                lines.append(f"  {g.get('goal_id','?')}: {g.get('title','?')} "
                             f"({g.get('task_count',0)} tasks, {g.get('status','?')})")
        return "\n".join(lines)
    # single card
    if "card" in out:
        c = out["card"]
        if isinstance(c, dict):
            top = ", ".join(f"{k}={v}" for k, v in
                            sorted((c.get("capacities") or {}).items(),
                                   key=lambda x: -x[1])[:3])
            top_s = f"Top capacity: {top}" if top else ""
            return (f"Agent: {c.get('agent_id','?')} ({c.get('name','?')})\n"
                    f"Bio: {c.get('bio','')}\n{top_s}")
    # task(s)
    if "task" in out:
        t = out["task"]
        if isinstance(t, dict):
            return (f"Task: {t.get('task_id','?')} — {t.get('title','?')} "
                    f"[{t.get('status','?')}]")
    if "tasks" in out:
        tasks = out["tasks"]
        if not tasks:
            return "(no tasks)"
        lines = ["📋 TASKS"]
        for t in (tasks if isinstance(tasks, list) else [tasks]):
            if isinstance(t, dict):
                lines.append(f"  {t.get('task_id','?')}: {t.get('title','?')} "
                             f"[{t.get('status','?')}]")
        return "\n".join(lines)
    # inbox
    if "inbox" in out:
        inbox = out["inbox"]
        if not inbox:
            return "(inbox empty)"
        lines = ["📬 YOUR INBOX", "─" * 50]
        for note in inbox if isinstance(inbox, list) else [inbox]:
            if isinstance(note, dict):
                author = note.get("author_agent_id", "?")
                kind = note.get("kind", "")
                text = note.get("text", "")[:150]
                ts = (note.get("ts", "") or "")[11:19] if note.get("ts") else ""
                lines.append(f"[{ts}] {author} ({kind}): {text}")
        return "\n".join(lines)
    # fallback: key-value dump
    lines = []
    for k, v in out.items():
        if k in ("ok", "error", "message", "content", "text"):
            continue
        if isinstance(v, list):
            lines.append(f"{k}: {len(v)} items")
        elif isinstance(v, dict):
            lines.append(f"{k}: {len(v)} fields")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) if lines else "ok"
