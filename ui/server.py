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
import sys
import threading
from pathlib import Path

# ── workspace root on path (run from anywhere) ───────────────────────────────
_WS = Path(__file__).resolve().parent.parent
if str(_WS) not in sys.path:
    sys.path.insert(0, str(_WS))

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402

from tools.config import Config  # noqa: E402
from tools.graph import KnowledgeGraph  # noqa: E402
from tools.encoder import EncoderLayer  # noqa: E402
from tools.build import build_graph, export_backward_compatible  # noqa: E402
from LLMs.deepseek import DeepSeekProvider, MockProvider  # noqa: E402
from tools.graph_tools import ensure_tools  # noqa: E402
from tools.agents import NodeAgent, GrowthAgent  # noqa: E402
from database.notes import NoteStore, Note  # noqa: E402
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

STATIC_DIR = Path(__file__).resolve().parent / "static"


AGENT_IDS = ["codex_normal", "codex_RAG", "codex_growth"]


def _make_codex_agents(provider_, store_, chat_mode: bool = False) -> dict:
    """Create the three shared codex agents (IPP) bound to graph + encoder."""
    from codex_normal import create_agent as mk_normal
    from codex_RAG import create_agent as mk_rag
    from codex_growth import create_agent as mk_growth
    from tools.api import ensure_tools as ensure_shared
    ensure_shared()
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


def _load_or_build() -> None:
    """Load the persisted graph if present, else build from assets."""
    global graph, encoder, provider, node_agent, growth_agent, store, codex_agents
    with _lock:
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
        ensure_tools()
        provider = _make_provider()
        node_agent = NodeAgent(graph, encoder, llm=provider)
        growth_agent = GrowthAgent(graph, encoder, llm=provider)
        store = NoteStore()
        # chat surface = READ-ONLY agents (file-write + mutation tools disabled)
        codex_agents = _make_codex_agents(provider, store, chat_mode=True)
        # auto-reopen the last-active note project (create-and-open UX)
        active = store.active_project()
        if active:
            try:
                store.open_project(active)
                store.load_to_graph(graph)
                graph.pagerank()
                logger.info("note project re-opened: %s", active)
            except ValueError:
                logger.warning("active project %s not found; starting fresh", active)
        logger.info("graph ready: %s", graph.summary().splitlines()[0])


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
    from tools.agent_specs import TOOL_SETS
    return jsonify({
        "ok": True,
        "workspace": str(Config.WORKSPACE_ROOT),
        "assets": str(Config.ASSETS_DIR),
        "provider": provider.name if provider else None,
        "model": Config.get_model(),
        "tools": [t.tool_name for t in __import__("tools.ipp", fromlist=["ToolRegistry"]).ToolRegistry.all()],
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
        nodes = [
            {"node_id": nid,
             "entryname": graph.get_node(nid).entryname if graph.get_node(nid) else nid,
             "score": round(score, 4)}
            for nid, score in encoder.search_nodes(query, k=k)
        ]
        chunks = [
            {"chunk_id": c.chunk_id, "section": c.section, "text": c.text[:220],
             "sim": round(sim, 4)}
            for c, sim in encoder.search(query, k=k)
        ]
        return jsonify({"nodes": nodes, "chunks": chunks})


# ── agents ────────────────────────────────────────────────────────────────────
@app.get("/api/agent/list")
def agent_list():
    """The three shared codex agents + their tool counts."""
    with _lock:
        from tools.agent_specs import TOOL_SETS, PROMPTS
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
        html = interactive_html(graph, anchor=nid if anchor else None,
                                depth=depth, title=title)
        # persist into the open project (if any)
        if store and store.current():
            out = store.project_dir / "interactive.html"
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
        return jsonify({"projects": store.list_projects(),
                        "current": store.current()})


@app.post("/api/database/create")
def db_create():
    body = request.get_json(force=True, silent=True) or {}
    name = body.get("name", "").strip()
    description = body.get("description", "")
    if not name:
        return jsonify({"error": "name required"}), 400
    with _lock:
        try:
            meta = store.create_project(name, description)
            return jsonify({"ok": True, "project": meta})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400


@app.post("/api/database/open")
def db_open():
    body = request.get_json(force=True, silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    with _lock:
        try:
            meta = store.open_project(name)
            # load the notes into the live graph (union)
            result = store.load_to_graph(graph)
            graph.pagerank()
            graph.save()
            return jsonify({"ok": True, "project": meta, **result})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404


@app.get("/api/database/notes")
def db_notes():
    with _lock:
        if not store.current():
            return jsonify({"notes": [], "project": None})
        return jsonify({"notes": store.list_notes(), "project": store.current()})


@app.get("/api/database/note/<node_id>")
def db_note(node_id: str):
    with _lock:
        if not store.current():
            return jsonify({"error": "no project open"}), 400
        try:
            note = store.get_note(node_id)
            return jsonify(note.to_dict())
        except FileNotFoundError:
            return jsonify({"error": f"note not found: {node_id}"}), 404


@app.post("/api/database/note/update")
def db_note_update():
    body = request.get_json(force=True, silent=True) or {}
    node_id = body.get("node_id")
    if not node_id:
        return jsonify({"error": "node_id required"}), 400
    with _lock:
        if not store.current():
            return jsonify({"error": "no project open"}), 400
        try:
            note = store.get_note(node_id)
        except FileNotFoundError:
            return jsonify({"error": f"note not found: {node_id}"}), 404
        if "content" in body:
            note.content = body["content"]
        if "description" in body:
            note.description = body["description"]
        author = body.get("author", "ui")
        summary = body.get("summary", "Updated via web UI.")
        note = store.save_note(note, author=author, summary=summary)
        return jsonify({"ok": True, "note": note.to_dict()})


@app.post("/api/database/sync")
def db_sync():
    """Write the current graph's nodes as .md notes (idempotent)."""
    body = request.get_json(force=True, silent=True) or {}
    with _lock:
        if not store.current():
            return jsonify({"error": "no project open"}), 400
        result = store.sync_from_graph(graph, force=body.get("force", False))
        graph.save()
        return jsonify({"ok": True, **result})


@app.post("/api/graph/rebuild")
def rebuild():
    global graph, encoder, node_agent, growth_agent, codex_agents
    with _lock:
        graph, encoder = build_graph()
        graph.pagerank()
        node_agent = NodeAgent(graph, encoder, llm=provider)
        growth_agent = GrowthAgent(graph, encoder, llm=provider)
        codex_agents = _make_codex_agents(provider, store, chat_mode=True)
        return jsonify({
            "ok": True,
            "nodes": len(graph._nodes),
            "edges": len(graph._edges),
            "chunks": encoder.index.size(),
        })


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Graph Knowledge Network UI")
    parser.add_argument("--host", default="127.0.0.3", help="bind host (default 127.0.0.3)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default 8000)")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = parser.parse_args()

    _load_or_build()
    logger.info("UI ready → http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
