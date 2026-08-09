"""
Graph Knowledge Network UI server — the web interface for the Graph Knowledge Network.

A self-contained Flask application exposing:
  • Global graph overview (stats, nodes, registry)
  • Depth-k local graphs for any node (visualization payloads)
  • Interactive PyVis-style + Mermaid visualizations
  • Vector RAG search over the encoder layer
  • Node agent execution (operate on a node via its local graph)
  • Growth agent execution (recursive self-improvement)
  • Note database: create/open projects where every node is a .md note
    with a Version Control Log (§4.4a)
  • Run log (VCL) and backward-compatible export summary

Bind host defaults to 127.0.0.3 (configurable via GRAPH_UI_HOST / --host).
Run from the workspace root:

    python ui/server.py                 # → http://127.0.0.3:8000
    python ui/server.py --port 5000     # → http://127.0.0.3:5000
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
from pathlib import Path

# ── workspace root on path (run from anywhere) ───────────────────────────────
_WS = Path(__file__).resolve().parent.parent
if str(_WS) not in sys.path:
    sys.path.insert(0, str(_WS))

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402

from general_tools.config import Config  # noqa: E402
from general_tools.graph import KnowledgeGraph  # noqa: E402
from general_tools.encoder import EncoderLayer  # noqa: E402
from general_tools.build import build_graph, export_backward_compatible  # noqa: E402
from LLMs.deepseek import DeepSeekProvider, MockProvider  # noqa: E402
from general_tools.agents import NodeAgent, GrowthAgent  # noqa: E402
from database.notes import NoteStore, Note  # noqa: E402
from database.construct import bind_database, database_node  # noqa: E402
from general_tools.construct import tools_node as _shared_tools_node  # noqa: E402
from ui.visuals import interactive_html, mermaid_flowchart  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("graph.ui")

# ── shared state (thread-safe) ────────────────────────────────────────────────
_lock = threading.RLock()
graph: KnowledgeGraph | None = None
encoder: EncoderLayer | None = None
provider: DeepSeekProvider | None = None
node_agent: NodeAgent | None = None
growth_agent: GrowthAgent | None = None
store: NoteStore | None = None
codex_agents: dict = {}   # {agent_id: engine} for codex_normal / codex_RAG / codex_growth
_platform: dict | None = None   # the Multi Agent platform (strict IPP v0.2.8)
CUSTOM_GRAPH_DIR: Optional[Path] = None   # set when serving --graph DIR

STATIC_DIR = Path(__file__).resolve().parent / "static"


AGENT_IDS = ["codex_normal", "codex_RAG", "codex_growth"]


def _make_codex_agents(provider_, store_, chat_mode: bool = False) -> dict:
    """Create the three shared codex agents (IPP) bound to graph + encoder."""
    from codex_normal import create_agent as mk_normal
    from codex_RAG import create_agent as mk_rag
    from codex_growth import create_agent as mk_growth
    kw = {"chat_mode": chat_mode} if chat_mode else {}
    return {
        "codex_normal": mk_normal(graph, encoder, llm=provider_, store=store_, **kw),
        "codex_RAG": mk_rag(graph, encoder, llm=provider_, store=store_, **kw),
        "codex_growth": mk_growth(graph, encoder, llm=provider_, store=store_, **kw),
    }


def _make_provider() -> DeepSeekProvider:
    """Real DeepSeek provider if the key is available, else offline mock."""
    try:
        p = DeepSeekProvider(model=Config.get_model())
        p.chat([{"role": "user", "content": "ping"}], max_tokens=4)
        logger.info("LLM provider: deepseek:%s (live)", p.model)
        return p
    except Exception as exc:  # noqa: BLE001
        logger.warning("DeepSeek unavailable (%s) → using MockProvider", exc)
        return MockProvider()


def _auto_open_supplements(store_: NoteStore, graph_: KnowledgeGraph) -> list[dict]:
    """Re-open the project's ACTIVE supplements (opt-in overlays persisted in
    project.json) so main + supplements stay consistent across sessions.
    Each open flows through the database node's guardrail envelope."""
    if not store_.current():
        return []
    opened = []
    for slug in store_.active_supplements():
        try:
            p = database_node().invoke(
                "supplement", {"op": "open", "slug": slug}).payload
            if p.get("ok"):
                opened.append({"slug": slug, "loaded": p.get("loaded", 0),
                               "edges_loaded": p.get("edges_loaded", 0)})
            else:
                logger.warning("supplement %s skipped: %s", slug,
                               p.get("message"))
        except ValueError as exc:  # noqa: BLE001
            logger.warning("supplement %s skipped: %s", slug, exc)
    return opened


def _load_or_build(graph_dir: Optional[Path] = None) -> None:
    """Load the persisted graph if present, else build from assets.

    ``graph_dir``: serve a custom graph folder (e.g. ``database/calabiyau3fold/graph_data``)
    containing ``knowledge_graph.json`` + ``vectors/index.json``. When set,
    the note-project merge is skipped (note projects belong to the default
    GraphRAG graph). Canonical layout: every project owns its artifacts under
    ``database/<project>/graph_data/`` (see database/README.md).
    """
    global graph, encoder, provider, node_agent, growth_agent, store, codex_agents
    global CUSTOM_GRAPH_DIR
    with _lock:
        CUSTOM_GRAPH_DIR = graph_dir
        if graph_dir is not None:
            gpath = graph_dir / "knowledge_graph.json"
            vpath = graph_dir / "vectors" / "index.json"
            graph = KnowledgeGraph(path=gpath, auto_load=False)
            encoder = EncoderLayer()
            if gpath.exists():
                logger.info("loading custom graph from %s", graph_dir)
                graph.load()
                if vpath.exists():
                    encoder.load(vpath)
                else:
                    # graph exists but no vector index yet: build one from the
                    # graph's own nodes — do NOT merge another project in
                    for nid, node in graph._nodes.items():
                        encoder.ingest_meta(nid, f"{node.entryname} {node.description}")
                    encoder.save(vpath)
            else:
                logger.info("building custom graph into %s", graph_dir)
                from general_tools.build_cy3 import build_cy3_graph
                graph, encoder = build_cy3_graph(out_dir=graph_dir)
        else:
            graph = KnowledgeGraph()
            encoder = EncoderLayer()
            if graph.path.exists() and (Config.VECTOR_DIR / "index.json").exists():
                logger.info("loading persisted graph from %s", graph.path)
                graph.load()
                encoder.load()
            else:
                logger.info("building graph from assets/")
                graph, encoder = build_graph()
        graph.pagerank()
        _shared_tools_node()
        provider = _make_provider()
        node_agent = NodeAgent(graph, encoder, llm=provider)
        growth_agent = GrowthAgent(graph, encoder, llm=provider)
        store = NoteStore()
        # the database IPP node — the store's single IPP surface
        # (Γ ⊩ database/IPP.json × 𝒢; the platform registers the same
        # node into its shared GraphContext as the 44th node). Every
        # database operation — UI, tools, agents — flows through its
        # guardrail envelopes with hash-chained audits.
        bind_database(store, graph)
        database_node()
        # the tools IPP node — the SHARED runtime's single IPP surface
        # (Γ ⊩ tools/IPP.json × 𝒢; the 45th node of the platform). Every
        # tool dispatch + graph/encoder/build/check operation flows
        # through its guardrail envelopes with hash-chained audits.
        from general_tools.construct import bind_tools, tools_node
        bind_tools(graph, encoder)
        tools_node()
        # chat surface = READ-ONLY agents (file-write + mutation tools disabled)
        codex_agents = _make_codex_agents(provider, store, chat_mode=True)
        # auto-reopen the last-active note project (create-and-open UX).
        # In custom-graph mode we still open the note project (so the Database
        # tab shows its notes) but skip the graph ⇄ notes merge (the custom
        # graph is already the authoritative source). In default mode the
        # active project REPLACES the graph (its notes become the graph) so
        # projects never accumulate into a mixed multi-graph view.
        active = store.active_project()
        if active:
            try:
                store.open_project(active)
                if graph_dir is None and store.list_notes():
                    graph.clear()
                    store.load_to_graph(graph)
                    # re-open the project's active supplements (opt-in overlays)
                    _auto_open_supplements(store, graph)
                    graph.pagerank()
                logger.info("note project re-opened: %s", active)
            except ValueError:
                logger.warning("active project %s not found; starting fresh", active)
        logger.info("graph ready: %s", graph.summary().splitlines()[0])
        # Construct the recursive agent IPP node at startup
        _load_recursive_module()


# ══════════════════════════════════════════════════════════════════════════════
# App factory
# ══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__, static_folder=None, static_url_path=None)
app.config["JSON_SORT_KEYS"] = False


# ── static SPA ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(STATIC_DIR, filename)


# ── health & config ───────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    from general_tools.agent_specs import TOOL_SETS
    return jsonify({
        "ok": True,
        "workspace": str(Config.WORKSPACE_ROOT),
        "assets": str(Config.ASSETS_DIR),
        "provider": provider.name if provider else None,
        "model": Config.get_model(),
        "available_models": Config.AVAILABLE_MODELS,
        "tools": [d.get("function", {}).get("name") for d in _shared_tools_node().invoke("list", {}).payload.get("definitions", [])],
        "agents": [{"id": a, "tools": len(TOOL_SETS.get(a, []))} for a in AGENT_IDS],
        "graph_file": str(graph.path) if graph else None,
    })


# ── graph overview ────────────────────────────────────────────────────────────
@app.get("/api/graph/summary")
def graph_summary():
    with _lock:
        return jsonify({
            "nodes": len(graph._nodes),
            "edges": len(graph._edges),
            "density": round(graph.density(), 4),
            "components": len(graph.connected_components()),
            "violations": len(graph.validate_consistency()),
            "pagerank_top": [
                {"node_id": nid, "entryname": graph._nodes[nid].entryname,
                 "score": round(score, 4)}
                for nid, score in sorted(graph.pagerank().items(),
                                         key=lambda x: x[1], reverse=True)[:8]
            ],
            "registry": graph.to_structurelist(),
        })


@app.get("/api/graph/nodes")
def graph_nodes():
    with _lock:
        nodes = []
        for nid, n in graph._nodes.items():
            nodes.append({
                "node_id": nid, "entryname": n.entryname, "category": n.category,
                "description": n.description[:200],
                "in_degree": n.stats.get("in_degree", 0),
                "out_degree": n.stats.get("out_degree", 0),
                "pagerank": round(n.stats.get("pagerank", 0.0), 4),
            })
        return jsonify({"nodes": nodes})


@app.get("/api/graph/edges")
def graph_edges():
    """All edges of the global graph (for the full-graph view)."""
    with _lock:
        edges = [
            {"source": e.source, "target": e.target, "relation": e.relation}
            for e in graph._edges.values()
        ]
        return jsonify({"edges": edges})


@app.get("/api/graph/node/<node_id>")
def graph_node(node_id: str):
    with _lock:
        nid = graph.resolve(node_id)
        if nid is None:
            return jsonify({"error": f"node not found: {node_id}"}), 404
        n = graph.get_node(nid)
        return jsonify({
            "node_id": n.node_id, "entryname": n.entryname, "category": n.category,
            "description": n.description, "content": n.content,
            "stats": n.stats, "version": n.version, "timestamps": n.timestamps,
            "incoming": [
                {"node_id": s, "entryname": graph._nodes[s].entryname, "relation": r}
                for s, r in graph.incoming(nid)
            ],
            "outgoing": [
                {"node_id": t, "entryname": graph._nodes[t].entryname, "relation": r}
                for t, r in graph.outgoing(nid)
            ],
        })


@app.get("/api/graph/local/<node_id>")
def graph_local(node_id: str):
    """Visualization payload for L_k(node) — nodes + edges of the ego network."""
    depth = int(request.args.get("depth", Config.LOCAL_DEPTH))
    with _lock:
        nid = graph.resolve(node_id)
        if nid is None:
            return jsonify({"error": f"node not found: {node_id}"}), 404
        local = graph.materialize_local(nid, depth=depth)
        return jsonify({
            "anchor": nid,
            "depth": depth,
            "stats": local.stats,
            "nodes": [
                {"node_id": n.node_id, "entryname": n.entryname, "category": n.category,
                 "description": n.description[:120]}
                for n in local.nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "relation": e.relation}
                for e in local.edges
            ],
            "paths": local.paths[:20],
        })


# ── vector search ─────────────────────────────────────────────────────────────
@app.post("/api/search")
def search():
    body = request.get_json(force=True, silent=True) or {}
    query = body.get("query", "")
    k = int(body.get("k", 10))
    if not query:
        return jsonify({"error": "query required"}), 400
    with _lock:
        # the encoder operation flows through the tools node's guardrail
        # envelope (ι_pre → π → Ω → ι_post → ρ → τ*) with an audit record
        from general_tools.construct import tools_node
        p = tools_node().invoke(
            "encoder", {"op": "search", "query": query, "k": k}).payload
        if not isinstance(p, dict) or not p.get("ok"):
            return jsonify({"error": (p.get("message")
                                       if isinstance(p, dict) else "failed")}), 500
        return jsonify({"nodes": p.get("nodes", []),
                        "chunks": p.get("chunks", [])})


# ── agents ────────────────────────────────────────────────────────────────────
@app.get("/api/agent/list")
def agent_list():
    """The three shared codex agents + their tool counts."""
    with _lock:
        from general_tools.agent_specs import TOOL_SETS, PROMPTS
        return jsonify({
            "agents": [
                {"id": a, "tools": len(TOOL_SETS.get(a, [])),
                 "prompt": PROMPTS.get(a, "")[:80]}
                for a in AGENT_IDS
            ],
        })


@app.post("/api/agent/chat")
def run_agent_chat():
    """
    Unified agent chat against the three shared codex agents.

    body: {agent: 'codex_normal'|'codex_RAG'|'codex_growth',
           node: optional anchor node, task: the message}
    """
    body = request.get_json(force=True, silent=True) or {}
    agent_id = body.get("agent", "codex_normal")
    node_ref = body.get("node", "")
    task = body.get("task", "")
    if agent_id not in codex_agents:
        return jsonify({"error": f"unknown agent {agent_id!r}; choices: {AGENT_IDS}"}), 400
    if not task:
        return jsonify({"error": "task required"}), 400
    with _lock:
        try:
            engine = codex_agents[agent_id]
            if node_ref and node_ref.strip():
                engine.bind_node(node_ref.strip())
            # run with full observable trace (thinking/message/tools + answer)
            answer, trace = engine.run_with_trace(task)
            # forward the full tool-result content (no 300-char truncation)
            trace = _full_trace(trace)
            return jsonify({
                "agent": agent_id,
                "node": node_ref.strip() or engine.node_id,
                "answer": answer,
                "tokens": engine._session_tokens,
                "trace": trace,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("codex agent %s failed", agent_id)
            return jsonify({"error": str(exc)}), 500


@app.post("/api/agent/chat/stream")
def run_agent_chat_stream():
    """
    STREAMING agent chat — Server-Sent Events.

    Each ToolCallEvent (thinking / message / tool_call / tool_result / text /
    done / error) is emitted as it happens, so the UI can render the agent's
    process progressively instead of waiting for the whole turn.

    Body: {agent, node, task}
    Returns: text/event-stream of `data: {json}` lines.
    """
    body = request.get_json(force=True, silent=True) or {}
    agent_id = body.get("agent", "codex_normal")
    node_ref = body.get("node", "")
    task = body.get("task", "")
    if agent_id not in codex_agents:
        return jsonify({"error": f"unknown agent {agent_id!r}; choices: {AGENT_IDS}"}), 400
    if not task:
        return jsonify({"error": "task required"}), 400

    def generate():
        engine = codex_agents[agent_id]
        if node_ref and node_ref.strip():
            engine.bind_node(node_ref.strip())
        try:
            for event in engine.chat_stream(task):
                payload = {"type": event.type}
                if event.tool is not None:
                    payload["tool"] = event.tool
                if event.args is not None:
                    payload["args"] = event.args
                if event.content is not None:
                    payload["content"] = event.content
                if event.error is not None:
                    payload["error"] = event.error
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            # terminal event
            yield f"data: {json.dumps({'type': 'end', 'agent': agent_id, 'tokens': engine._session_tokens}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("codex agent %s stream failed", agent_id)
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _full_trace(trace: list[dict]) -> list[dict]:
    """Ensure trace entries carry the full content (the engine truncates display)."""
    out = []
    for entry in trace:
        e = dict(entry)
        if e.get("type") == "tool_result" and e.get("content"):
            e["content"] = e["content"]
        out.append(e)
    return out


@app.post("/api/agent/node")
def run_node_agent():
    body = request.get_json(force=True, silent=True) or {}
    node_ref = body.get("node")
    task = body.get("task")
    if not node_ref or not task:
        return jsonify({"error": "node and task required"}), 400
    with _lock:
        try:
            result = node_agent.operate(node_ref, task, verbose=False)
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("node agent failed")
            return jsonify({"error": str(exc)}), 500


@app.post("/api/agent/grow")
def run_growth_agent():
    body = request.get_json(force=True, silent=True) or {}
    node_ref = body.get("node")
    topic = body.get("topic")
    motivation = body.get("motivation", "")
    if not node_ref or not topic:
        return jsonify({"error": "node and topic required"}), 400
    with _lock:
        try:
            result = growth_agent.expand(node_ref, topic, motivation)
            graph.save()
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("growth agent failed")
            return jsonify({"error": str(exc)}), 500


# ── runs & export ─────────────────────────────────────────────────────────────
@app.get("/api/runs")
def runs():
    with _lock:
        return jsonify({"runs": graph.runs()[-50:]})


@app.get("/api/export")
def export_info():
    with _lock:
        out = export_backward_compatible(graph)
        return jsonify({
            "path": str(out),
            "registry_entries": len(graph.to_structurelist()),
            "edge_files": len(graph.to_edges_files()),
        })


# ══════════════════════════════════════════════════════════════════════════════
# Visualizations
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/visual/interactive")
def visual_interactive():
    """PyVis-style interactive HTML for the whole graph or a local graph."""
    anchor = request.args.get("node")
    depth = int(request.args.get("depth", 3))
    with _lock:
        title = "Graph Knowledge Network"
        if anchor:
            nid = graph.resolve(anchor)
            if nid is None:
                return jsonify({"error": f"node not found: {anchor}"}), 404
            node = graph.get_node(nid)
            title = f"L{depth}({node.entryname})"
        colors = None
        if store and store.current():
            cp = database_node().invoke("categories", {"op": "get"}).payload
            colors = {"default": cp.get("default", "#8aa0b0"),
                      "map": cp.get("map", {})}
        html = interactive_html(graph, anchor=nid if anchor else None,
                                depth=depth, title=title,
                                category_colors=colors)
        # persist into the open project's graph_data/ (cached snapshot — the
        # page itself is always generated fresh from the in-memory graph)
        if store and store.current():
            out = store.graph_data_dir() / "interactive.html"
            out.write_text(html, encoding="utf-8")
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/api/visual/mermaid")
def visual_mermaid():
    """Mermaid dependency flowchart (the ScientificInfrastructure format)."""
    anchor = request.args.get("node")
    depth = int(request.args.get("depth", 3))
    with _lock:
        nid = graph.resolve(anchor) if anchor else None
        src = mermaid_flowchart(graph, anchor=nid, depth=depth)
        return jsonify({"mermaid": src})


# ══════════════════════════════════════════════════════════════════════════════
# Note database (project store)
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/database/projects")
def db_projects():
    with _lock:
        p = database_node().invoke("project", {"op": "list"}).payload
        return jsonify({"projects": p.get("projects", []),
                        "current": p.get("current")})


@app.post("/api/database/create")
def db_create():
    body = request.get_json(force=True, silent=True) or {}
    name = body.get("name", "").strip()
    description = body.get("description", "")
    if not name:
        return jsonify({"error": "name required"}), 400
    with _lock:
        p = database_node().invoke(
            "project", {"op": "create", "name": name,
                        "description": description}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 400
        return jsonify({"ok": True, "project": p["project"]})


@app.post("/api/database/open")
def db_open():
    body = request.get_json(force=True, silent=True) or {}
    name = body.get("name", "").strip()
    # replace=True (default): clear the live graph and load ONLY this
    # project's notes — one project = one graph. replace=False merges the
    # project's notes into whatever is currently loaded (union mode).
    replace = bool(body.get("replace", True))
    if not name:
        return jsonify({"error": "name required"}), 400
    with _lock:
        # Γ ⊩ database/IPP.json: the store mutation flows through the
        # node's guardrail envelope (project.open = open + load + persist)
        p = database_node().invoke(
            "project", {"op": "open", "name": name, "replace": replace}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 404
        meta = p["project"]
        supplements_opened = []
        if replace:
            # re-open the project's active supplements (opt-in overlays)
            supplements_opened = _auto_open_supplements(store, graph)
        graph.pagerank()
        # In custom-graph mode the seed graph file stays authoritative —
        # never overwrite it with another project's nodes. In default
        # mode persist the (replaced) graph to the OPEN project's own
        # graph_data/ (canonical layout — graph.path follows the project).
        if CUSTOM_GRAPH_DIR is None:
            target = store.graph_data_dir() / "knowledge_graph.json"
            graph.path = target
            graph.save(target)
        return jsonify({
            "ok": True, "project": meta, "replaced": replace,
            "supplements_opened": supplements_opened,
            "loaded": p.get("loaded"), "nodes": p.get("nodes"),
            "edges": p.get("edges")})


@app.get("/api/database/supplements")
def db_supplements():
    """List a project's supplement bundles (slug, name, counts, active).
    ``?project=<slug>`` scopes to the SELECTED project without switching the
    server's open project — so the UI dropdown always matches what the user
    picked, never a stale server-side "current"."""
    with _lock:
        proj = request.args.get("project") or (store.current() if store else None)
        if not proj:
            return jsonify({"supplements": [], "project": None})
        p = database_node().invoke(
            "supplement", {"op": "list", "project": proj}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 404
        return jsonify({"supplements": p.get("supplements", []),
                        "project": proj})


@app.post("/api/database/supplement/create")
def db_supplement_create():
    body = request.get_json(force=True, silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    proj = body.get("project") or (store.current() if store else None)
    with _lock:
        if not proj:
            return jsonify({"error": "no project open"}), 400
        p = database_node().invoke(
            "supplement", {"op": "create", "name": name,
                           "description": body.get("description", ""),
                           "project": proj}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 400
        return jsonify({"ok": True, "supplement": p["supplement"]})


@app.post("/api/database/supplement/open")
def db_supplement_open():
    """Merge a supplement's notes into the live graph + persist (the node's
    supplement.open flows through the guardrail envelope; project switching
    is handled inside the impl — one store surface).
    ``project`` optional — defaults to the open project."""
    body = request.get_json(force=True, silent=True) or {}
    slug = body.get("supplement", "").strip()
    proj = body.get("project") or (store.current() if store else None)
    if not slug:
        return jsonify({"error": "supplement slug required"}), 400
    with _lock:
        if not proj:
            return jsonify({"error": "no project open"}), 400
        p = database_node().invoke(
            "supplement", {"op": "open", "slug": slug, "project": proj}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 404
        return jsonify({"ok": True, "supplement": slug,
                        "loaded": p.get("loaded", 0),
                        "edges_loaded": p.get("edges_loaded", 0)})


@app.post("/api/database/supplement/close")
def db_supplement_close():
    """Remove a supplement's nodes/edges from the live graph + persist
    (via the database node's guardrail envelope).
    ``project`` optional — defaults to the open project."""
    body = request.get_json(force=True, silent=True) or {}
    slug = body.get("supplement", "").strip()
    proj = body.get("project") or (store.current() if store else None)
    if not slug:
        return jsonify({"error": "supplement slug required"}), 400
    with _lock:
        if not proj:
            return jsonify({"error": "no project open"}), 400
        p = database_node().invoke(
            "supplement", {"op": "close", "slug": slug, "project": proj}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 404
        return jsonify({"ok": True, "supplement": slug,
                        "removed_nodes": p.get("removed_nodes", 0),
                        "removed_edges": p.get("removed_edges", 0)})


@app.get("/api/database/categories")
def db_categories():
    """A project's category→color map (categories.json). ``?project=`` scopes
    to the SELECTED project without switching; defaults to the open one."""
    with _lock:
        proj = request.args.get("project") or (store.current() if store else None)
        if not proj:
            return jsonify({"project": None, "default": "#8aa0b0", "map": {}})
        p = database_node().invoke(
            "categories", {"op": "get", "project": proj}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 404
        return jsonify({"project": p.get("project"),
                        "default": p.get("default"),
                        "map": p.get("map", {})})


@app.post("/api/database/categories")
def db_categories_update():
    """Update the open project's category→color map: {map: {cat: hex}, default?}."""
    body = request.get_json(force=True, silent=True) or {}
    with _lock:
        if not store or not store.current():
            return jsonify({"error": "no project open"}), 400
        p = database_node().invoke(
            "categories", {"op": "update",
                           "map": body.get("map") or {},
                           "default": body.get("default")}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 400
        return jsonify({"ok": True, "project": p.get("project"),
                        "default": p.get("default"),
                        "map": p.get("map", {})})


@app.get("/api/database/notes")
def db_notes():
    with _lock:
        p = database_node().invoke("nodes", {"op": "list_notes"}).payload
        return jsonify({"notes": p.get("notes", []),
                        "project": p.get("project")})


@app.get("/api/database/note/<node_id>")
def db_note(node_id: str):
    with _lock:
        if not store.current():
            return jsonify({"error": "no project open"}), 400
        p = database_node().invoke(
            "nodes", {"op": "get_note", "node_id": node_id}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message",
                                            f"note not found: {node_id}")}), \
                (404 if p.get("error") == "not_found" else 400)
        return jsonify(p["note"])


@app.post("/api/database/note/update")
def db_note_update():
    body = request.get_json(force=True, silent=True) or {}
    node_id = body.get("node_id")
    if not node_id:
        return jsonify({"error": "node_id required"}), 400
    with _lock:
        if not store.current():
            return jsonify({"error": "no project open"}), 400
        payload = {"node_id": node_id, "op": "update_note"}
        if "content" in body:
            payload["content"] = body["content"]
        if "description" in body:
            payload["description"] = body["description"]
        payload["author"] = body.get("author", "ui")
        payload["summary"] = body.get("summary", "Updated via web UI.")
        p = database_node().invoke("nodes", payload).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), \
                (404 if p.get("error") == "not_found" else 400)
        return jsonify({"ok": True, "note": p["note"]})


@app.post("/api/database/sync")
def db_sync():
    """Write the current graph's nodes as .md notes (idempotent).
    Flows through the database node's guardrail envelope (graph.sync)."""
    body = request.get_json(force=True, silent=True) or {}
    with _lock:
        if not store.current():
            return jsonify({"error": "no project open"}), 400
        p = database_node().invoke(
            "graph", {"op": "sync",
                      "force": bool(body.get("force", False))}).payload
        if not p.get("ok"):
            return jsonify({"error": p.get("message", "failed")}), 400
        target = store.graph_data_dir() / "knowledge_graph.json"
        graph.path = target
        return jsonify({"ok": True, "created": p.get("created"),
                        "updated": p.get("updated"),
                        "skipped": p.get("skipped", 0)})


@app.post("/api/graph/rebuild")
def rebuild():
    global graph, encoder, node_agent, growth_agent, codex_agents, provider, _platform
    with _lock:
        _platform = None   # agents hold the old graph — rebuild the platform
        if CUSTOM_GRAPH_DIR is not None:
            from general_tools.build_cy3 import build_cy3_graph
            graph, encoder = build_cy3_graph(out_dir=graph.path.parent)
        else:
            graph, encoder = build_graph()
        graph.pagerank()
        node_agent = NodeAgent(graph, encoder, llm=provider)
        growth_agent = GrowthAgent(graph, encoder, llm=provider)
        codex_agents = _make_codex_agents(provider, store, chat_mode=True)
        # the database node reads the graph LIVE from the shared bridge —
        # rebind so its handlers operate on the fresh graph (audit history
        # is preserved: one node, one audit trail per process)
        bind_database(store, graph)
        # same for the tools node (the shared runtime's live bindings)
        from general_tools.construct import bind_tools
        bind_tools(graph, encoder)
        return jsonify({
            "ok": True,
            "nodes": len(graph._nodes),
            "edges": len(graph._edges),
            "chunks": encoder.index.size(),
        })


# ══════════════════════════════════════════════════════════════════════════════
# Multi Agent platform — strict IPP v0.2.8 (social_activity + 20 agents + portal)
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_platform():
    """Lazily assemble the Multi Agent platform (one shared GraphContext 𝒢).

    Built on first request so the base control center boots fast; every
    runtime interaction flows through IPP guardrail envelopes.
    """
    global _platform
    with _lock:
        if _platform is None:
            from IPP_Social.integration import build_platform
            logger.info("assembling Multi Agent platform (strict IPP v0.2.8)…")
            _platform = build_platform(
                graph, encoder, provider, store,
                agent_chat_mode=True, max_concurrent=4)
            n_nodes = len(_platform["ctx"].registry)
            logger.info("platform ready: %d IPP nodes in 𝒢 (portal=%s, "
                        "swarm=%d runtimes)", n_nodes,
                        _platform["portal_node"].node_id,
                        len(_platform["runtimes"]))
    return _platform


def _refresh_platform() -> dict:
    """Stop the current Multi Agent platform and rebuild it fresh.

    Stops the conversation responder + all agent runtimes (queued tasks
    dropped), then rebuilds the 43-node platform (same GraphContext
    pattern) — used by the Settings tab's "refresh services" button.
    """
    global _platform
    with _lock:
        if _platform is not None:
            try:
                _platform["swarm"].stop_responder()
                _platform["swarm"].stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("platform stop during refresh: %s", exc)
            _platform = None
        from IPP_Social.integration import build_platform
        _platform = build_platform(graph, encoder, provider, store,
                                   agent_chat_mode=True, max_concurrent=4)
        n_nodes = len(_platform["ctx"].registry)
        logger.info("platform refreshed: %d IPP nodes in 𝒢 (portal=%s, "
                    "swarm=%d runtimes)", n_nodes,
                    _platform["portal_node"].node_id,
                    len(_platform["runtimes"]))
        return {
            "ok": True,
            "nodes": n_nodes,
            "runtimes": len(_platform["runtimes"]),
            "settings": _platform.get("settings")
            and _platform["settings"].all() or None,
        }


def _portal_invoke(channel: str, payload: dict):
    """Invoke the portal node through its guardrail envelope.

    None-valued fields are stripped so optional keys pass the port
    schemas (O1 input conformance).
    """
    platform = _ensure_platform()
    clean = {k: v for k, v in payload.items() if v is not None}
    return platform["portal_node"].invoke(channel, clean).payload


@app.get("/api/social/agents")
def social_agents():
    """Agent cards + swarm runtime status + IPP addresses (portal.discover)."""
    try:
        return jsonify(_portal_invoke("discover", {"op": "agents"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social agents failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/social/board")
def social_board():
    """The global chat board messages (portal.discover.board)."""
    try:
        return jsonify(_portal_invoke("discover", {"op": "board"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social board failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/social/board")
def social_board_post():
    """Post to the global chat board as the user (portal.command.board)."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("command", {
            "op": "board", "author_agent_id": "user",
            "text": body.get("text", ""), "tags": body.get("tags"),
            "to_agent_id": body.get("to_agent_id", "")}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social board post failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/social/goal")
def social_goal_detail():
    """One goal folder with its tasks (portal.discover.goal_detail)."""
    goal_id = request.args.get("goal_id", "")
    try:
        return jsonify(_portal_invoke("discover", {"op": "goal_detail",
                                                    "goal_id": goal_id}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social goal detail failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/social/goal/delete")
def social_delete_goal():
    """Permanently delete a goal folder (portal.command.delete_goal)."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("command", {
            "op": "delete_goal", "goal_id": body.get("goal_id", "")}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social goal delete failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/social/board/clear")
def social_clear_board():
    """Clear the chat: scope 'inter' = agent-authored only, 'all' = everything."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("command", {
            "op": "clear_chat", "scope": body.get("scope", "all")}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social board clear failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/services/refresh")
def services_refresh():
    """Refresh the Multi Agent services (stop + rebuild the platform).

    Stops the conversation responder and all agent runtimes, then
    rebuilds the 43-node platform fresh (Settings tab → refresh).
    """
    try:
        result = _refresh_platform()
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("services refresh failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/settings")
def settings_get():
    """The Multi Agent platform settings (portal.settings.get)."""
    try:
        return jsonify(_portal_invoke("settings", {"op": "get"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("settings get failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/settings")
def settings_set():
    """Update the platform settings (portal.settings.set)."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("settings", {"op": "set",
                                                   "settings": body}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("settings set failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/social/goals")
def social_goals():
    """All goal folders with their tasks (portal.discover.goals)."""
    try:
        return jsonify(_portal_invoke("discover", {"op": "goals"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social goals failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/social/goal")
def social_create_goal():
    """Name a goal — create the goal folder in the social database."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("command", {
            "op": "goal", "title": body.get("title", ""),
            "description": body.get("description", "")}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social goal failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/social/instruct")
def social_instruct():
    """Give one individual agent a direct instruction (portal.command)."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("command", {
            "op": "instruct", "agent_id": body.get("agent_id", ""),
            "instruction": body.get("instruction", ""),
            "goal_id": body.get("goal_id")}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("social instruct failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/swarm/start")
def swarm_start():
    """Start many agents together under one goal (portal.swarm.start).

    ``goal_id`` reuses an EXISTING goal folder (continue) instead of
    creating a new one.
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(_portal_invoke("swarm", {
            "op": "start", "goal": body.get("goal", ""),
            "instructions": body.get("instructions", ""),
            "agent_ids": body.get("agent_ids"),
            "goal_id": body.get("goal_id")}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("swarm start failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/swarm/stop")
def swarm_stop():
    """Stop all runtimes (portal.swarm.stop)."""
    try:
        return jsonify(_portal_invoke("swarm", {"op": "stop"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("swarm stop failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/swarm/status")
def swarm_status():
    """Per-agent status + aggregate counters (portal.swarm.status)."""
    try:
        return jsonify(_portal_invoke("swarm", {"op": "status"}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("swarm status failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/swarm/events")
def swarm_events():
    """SSE: live multi-agent activity (portal.monitor over the swarm bus)."""
    platform = _ensure_platform()
    since = int(request.args.get("since", 0) or 0)

    def generate():
        try:
            for ev in platform["swarm"].bus.iter_live(since=since):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("swarm events stream ended: %s", exc)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ══════════════════════════════════════════════════════════════════════════════
# Recursive Agent portal — IPP v0.2.8 interface
#
# The Flask server does NOT import agent internals. ALL operations go
# through the recursive_agent_module IPP node's guardrail envelope:
#   server.py  →  ra_node.invoke(channel, payload)
# ══════════════════════════════════════════════════════════════════════════════

_ra_node = None  # constructed by _load_or_build / _load_recursive_module


def _load_recursive_module():
    """Construct the recursive agent IPP node (called once at startup)."""
    global _ra_node
    from recursive_agents.recursive_agent_module._ctor import construct_ra_node
    _ra_node = construct_ra_node(_lock, graph=graph, encoder=encoder, provider=provider)


def _ra_invoke(channel: str, payload: dict) -> dict:
    """Invoke a channel on the recursive agent IPP node.
    Returns the payload dict from the response."""
    try:
        if _ra_node is None:
            _load_recursive_module()
        result = _ra_node.invoke(channel, payload)
        p = result.payload
        return p if isinstance(p, dict) else {"ok": False, "error": str(p)}
    except Exception as exc:
        import traceback
        logger.exception("ra_invoke(%s) failed", channel)
        return {"ok": False, "error": str(exc),
                "traceback": traceback.format_exc()[-800:]}


@app.get("/api/recursive/chain")
def recursive_chain():
    return jsonify(_ra_invoke("chain", {}))


@app.post("/api/recursive/chat")
def recursive_chat():
    """Simple chat with a recursive agent — returns full trace + final answer."""
    import traceback as _tb, re as _re
    body = request.get_json(force=True, silent=True) or {}
    agent_id = (body.get("agent_id") or "").strip()
    message = (body.get("message") or "").strip()
    live = body.get("live", True)
    model_id = (body.get("model") or Config.DEFAULT_MODEL).strip()
    if not agent_id or not message:
        return jsonify({"ok": False, "error": "agent_id and message required"}), 400

    try:
        with _lock:
            from recursive_agents.agent_a1.agent_a1_tools.tool_registry import AgentA1Toolkit
            from recursive_agents.runtime.engine import RecursiveAgentEngine
            from LLMs.deepseek import MockProvider

            # Per-request provider: independent per-portal model selection
            llm_for_chat = DeepSeekProvider(model=model_id) if live else MockProvider()
            tk = AgentA1Toolkit(agent_id=agent_id, ws_root=str(Config.WORKSPACE_ROOT),
                                graph=graph, encoder=encoder, llm=llm_for_chat)
            tk.register_all()
            m = _re.search(r"agent_a(\d+)", agent_id)
            level = int(m.group(1)) if m else 1

            engine = RecursiveAgentEngine(graph=graph, encoder=encoder, llm=llm_for_chat,
                                          agent_id=agent_id, level=level, toolkit=tk)
            # Use chat_stream for full trace visibility, deduplicating text/message
            trace_events = []
            answer = ""
            last_content = None  # deduplicate consecutive identical content
            for event in engine.chat_stream(message):
                step = {"type": event.type}
                content_str = None

                if event.tool:
                    step["tool"] = event.tool
                    step["args"] = event.args
                if event.content and event.type in ("text", "message"):
                    content_str = str(event.content)
                    # Accumulate for final answer (text events only)
                    if event.type == "text" and event.content:
                        answer += (event.content or "")
                    # Also accumulate from messages for non-tool answers
                    if event.type == "message" and (event.content or "") and not answer:
                        answer += (event.content or "")
                if event.type == "thinking":
                    content_str = str(event.content or "")
                    step["content"] = content_str
                if event.type == "tool_result":
                    content_str = str(event.content or "")[:1000]
                    step["content"] = content_str
                if event.error:
                    step["error"] = event.error

                # Deduplicate: skip if same content as the previous entry
                if content_str is not None and content_str == last_content:
                    continue
                last_content = content_str

                if content_str is not None and event.type in ("text", "message"):
                    step["content"] = content_str[:2000]

                if step.get("content") or step.get("tool") or step.get("error"):
                    trace_events.append(step)

            # Strip the duplicate from answer (engine often wraps text in both message+text)
            answer = answer.strip()[:5000]
            # Remove duplicate paragraphs
            paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
            seen = set()
            deduped = []
            for p in paragraphs:
                key = p[:80]
                if key not in seen:
                    seen.add(key)
                    deduped.append(p)
            answer = "\n\n".join(deduped)

            return jsonify({
                "ok": True, "agent_id": agent_id,
                "answer": answer.strip()[:5000],
                "trace": trace_events[-60:],
                "tool_calls": sum(1 for e in trace_events if e.get("type") == "tool_call"),
                "tools_used": sorted(set(e.get("tool","") for e in trace_events if e.get("tool"))),
            })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                       "traceback": _tb.format_exc()[-800:]}), 500


@app.route("/api/recursive/instruct", methods=["POST"])

def recursive_instruct():
    import sys as _sys
    body = request.get_json(force=True, silent=True) or {}
    agent_id = (body.get("agent_id") or "").strip()
    task = (body.get("task") or "").strip()
    model_id = (body.get("model") or Config.DEFAULT_MODEL).strip()
    _sys.stderr.write(f"RECURSIVE_INSTRUCT: agent={agent_id} task={task[:50]}\n")
    _sys.stderr.flush()
    
    if not agent_id or not task:
        return jsonify({"ok": False, "error": "agent_id and task required"}), 400

    try:
        with _lock:
            # Step 1: import toolkit
            from recursive_agents.agent_a1.agent_a1_tools.tool_registry import AgentA1Toolkit
            tk = AgentA1Toolkit(agent_id=agent_id, ws_root=str(Config.WORKSPACE_ROOT),
                                graph=graph, encoder=encoder,
                                llm=DeepSeekProvider(model=model_id))
            tk.register_all()
            _sys.stderr.write(f"RECURSIVE_INSTRUCT: toolkit ready ({tk.count()} tools)\n")
            _sys.stderr.flush()

            # Step 2: create engine
            from recursive_agents.runtime.engine import RecursiveAgentEngine
            import re
            m = re.search(r"agent_a(\d+)", agent_id)
            level = int(m.group(1)) if m else 1
            engine = RecursiveAgentEngine(graph=graph, encoder=encoder,
                                          llm=DeepSeekProvider(model=model_id),
                                          agent_id=agent_id, level=level, toolkit=tk)
            _sys.stderr.write(f"RECURSIVE_INSTRUCT: engine ready, starting chat_stream\n")
            _sys.stderr.flush()

            # Step 3: run
            answer = engine.chat(task)
            _sys.stderr.write(f"RECURSIVE_INSTRUCT: done, answer={answer[:100]}\n")
            _sys.stderr.flush()

            return jsonify({"ok": True, "agent_id": agent_id, "answer": answer[:2000],
                           "chain": list(tk.chain), "constructed": sorted(tk.constructed)})

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        _sys.stderr.write(f"RECURSIVE_INSTRUCT FAIL: {exc}\n{tb[-600:]}\n")
        _sys.stderr.flush()
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                       "traceback": tb[-1000:]}), 500


@app.post("/api/recursive/instruct-offline")
def recursive_instruct_offline():
    body = request.get_json(force=True, silent=True) or {}
    payload = _ra_invoke("instruct_offline", body)
    status = 200 if payload.get("ok") else 500
    return jsonify(payload), status


@app.post("/api/recursive/verify")
def recursive_verify():
    body = request.get_json(force=True, silent=True) or {}
    payload = _ra_invoke("verify", body)
    status = 200 if payload.get("ok") else 500
    return jsonify(payload), status


@app.post("/api/recursive/diff")
def recursive_diff():
    body = request.get_json(force=True, silent=True) or {}
    payload = _ra_invoke("diff", body)
    status = 200 if payload.get("ok") else 500
    return jsonify(payload), status


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Graph Knowledge Network UI")
    parser.add_argument("--host", default="127.0.0.3", help="bind host (default 127.0.0.3)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default 8000)")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    parser.add_argument(
        "--graph", default=None, metavar="DIR",
        help="serve a custom graph folder with knowledge_graph.json + "
             "vectors/index.json (e.g. database/calabiyau3fold/graph_data "
             "for the Calabi-Yau graph)",
    )
    args = parser.parse_args()

    _load_or_build(Path(args.graph) if args.graph else None)
    logger.info("UI ready → http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
