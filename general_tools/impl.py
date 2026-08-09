"""
tools.impl — the SHARED runtime operations (single source of truth).

Pure domain logic for the ``tools`` IPP node: the invoke ROUTER (R*_k),
the definition catalog, and the graph/encoder/build/check operations.
Every ``impl_*`` function returns a structured ``{"ok": bool, ...}``
dict. This module contains NO tools and NO IPP logic — it is called by
the tools node's Ω handlers (tools.IPP_object).

The shared runtime is bound LIVE through tools.construct (bind_tools /
current_graph / current_encoder / current_agents) — rebinds are honored
without re-construction (I1: F stays untouched).

Node channels ↔ impl families:
  invoke      impl_execute_tool      — route a tool name → target envelope
  list        impl_list_tools        — definitions from the F-file catalog
  describe    impl_describe_tool     — one definition from the catalog
  graph       impl_graph_op          — local/read/validate/summarize/stats/…
  encoder     impl_encoder_op        — search_nodes/search/ingest/save
  build       impl_build_op          — build/cy3/export
  check       impl_check_op          — review/standard/advanced audits
  (19 codex channels)                — the codex_tools functions as handlers
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from general_tools.config import Config

logger = logging.getLogger("general_tools.impl")

__all__ = [
    "impl_execute_tool", "impl_list_tools", "impl_describe_tool",
    "impl_graph_op", "impl_encoder_op", "impl_build_op", "impl_check_op",
    "SKIP_DIRS", "THREAT_PATTERNS",
]


# ══════════════════════════════════════════════════════════════════════════
# invoke — the ROUTER (R*_k): name → the target channel's guardrail envelope
# ══════════════════════════════════════════════════════════════════════════

def _target_node(node_key: str, channel: str, op: Optional[str],
                 payload: dict):
    """Resolve the route target and invoke it. Returns the payload dict.

    - "self"           → a tools-node channel (its OWN envelope — the
                         second hop of the chain, both audited)
    - "database"       → the database node (process singleton)
    - "social_activity"→ the social node (bound by the platform)
    """
    from general_tools.construct import tools_node
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
        from general_tools.construct import current_social_node
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
            cap = c.get("capacity", {})
            top = sorted(cap.items(), key=lambda x: float(x[1] or 0), reverse=True)[:3]
            top_s = ", ".join(f"{k}={v}" for k, v in top)
            return (f"Agent: {c.get('agent_id','?')} ({c.get('name','?')})\n"
                    f"Bio: {c.get('bio','')}\nTop capacity: {top_s}")
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


# ══════════════════════════════════════════════════════════════════════════
# list / describe — the definitions from the F-file catalog
# ══════════════════════════════════════════════════════════════════════════


def _catalog():
    from general_tools.construct import current_catalog
    cat = current_catalog()
    if not cat:
        from general_tools.catalog import build_catalog
        cat = build_catalog()
    return cat


def impl_list_tools(args: dict) -> dict:
    """{names?, round_index?} → {ok, definitions, count, names}."""
    names = args.get("names")
    cat = _catalog()
    chosen = sorted(cat) if not names else \
        [n for n in names if n in cat]
    defs = []
    for n in chosen:
        d = _definition_of(cat, n)
        if d:
            defs.append(d)
    return {"ok": True, "definitions": defs, "count": len(defs),
            "names": chosen}


def impl_describe_tool(args: dict) -> dict:
    """{tool} → {ok, definition, source}."""
    name = str(args.get("tool", ""))
    d = _definition_of(_catalog(), name)
    if d is None:
        return {"ok": False, "error": "unknown_tool",
                "message": f"unknown tool {name!r}", "definition": None}
    return {"ok": True, "definition": d, "source": "f-file-catalog"}


def _definition_of(cat: dict, name: str) -> Optional[dict]:
    from general_tools.catalog import definition
    return definition(cat, name)


# ══════════════════════════════════════════════════════════════════════════
# graph — the agent's hands on the network (local graphs, reads, audits)
# ══════════════════════════════════════════════════════════════════════════


def _graph():
    from general_tools.construct import current_graph
    return current_graph()


def impl_graph_op(args: dict) -> dict:
    """{op: local|read|validate|summarize|stats|pagerank|registry, ...}.
    A graph passed IN the payload wins (per-agent instances via the
    router); otherwise the bridge's current graph is used."""
    graph = args.get("graph") or _graph()
    if graph is None:
        return {"ok": False, "error": "no_graph_bound",
                "message": "no graph bound to the tools node"}
    op = args.get("op")
    if op == "local":
        anchor = graph.resolve(args["node_id"])
        if anchor is None:
            return {"ok": False, "error": "not_found",
                    "message": f"node not found: {args['node_id']}"}
        local = graph.materialize_local(
            anchor, depth=int(args.get("depth") or Config.LOCAL_DEPTH))
        return {"ok": True,
                "content": local.verbalize(),
                "node_count": local.node_count(),
                "edge_count": local.edge_count(),
                "stats": local.stats}
    if op == "read":
        node = graph.get_node(graph.resolve(args["node_id"]))
        if node is None:
            return {"ok": False, "error": "not_found",
                    "message": f"node not found: {args['node_id']}"}
        payload = {
            "node_id": node.node_id, "entryname": node.entryname,
            "category": node.category,
            "description": str(node.description or "")[:300],
            "content": node.content, "stats": node.stats,
            "version": node.version,
        }
        return {"ok": True, "node": payload,
                "content": json.dumps(payload, ensure_ascii=False, indent=1)}
    if op == "validate":
        violations = graph.validate_consistency()
        comps = graph.connected_components()
        lines = [graph.summary(),
                 f"consistency violations: {len(violations)}",
                 f"weakly-connected components: {len(comps)}"]
        if violations:
            lines += [f"  !! {v}" for v in violations[:5]]
        return {"ok": True, "content": "\n".join(lines),
                "violations": len(violations), "components": len(comps)}
    if op == "summarize":
        anchor = graph.resolve(args["node_id"])
        if anchor is None:
            return {"ok": False, "error": "not_found",
                    "message": f"node not found: {args['node_id']}"}
        local = graph.materialize_local(anchor, depth=Config.LOCAL_DEPTH)
        names = [n.entryname for n in local.nodes.values()]
        focus = args.get("focus", "")
        summary = (
            f"Local graph of {anchor} (depth {local.depth}): "
            f"{len(names)} nodes, {len(local.edges)} edges. "
            f"Nodes: {', '.join(names[:25])}"
            + (f"… Focus: {focus}" if focus else ""))
        return {"ok": True, "content": summary,
                "nodes": len(names), "edges": len(local.edges)}
    if op == "stats":
        return {"ok": True, "nodes": len(graph._nodes),
                "edges": len(graph._edges),
                "density": round(graph.density(), 4),
                "components": len(graph.connected_components()),
                "violations": len(graph.validate_consistency())}
    if op == "pagerank":
        top = sorted(graph.pagerank().items(),
                     key=lambda x: x[1], reverse=True)[:8]
        return {"ok": True,
                "top": [{"node_id": nid, "score": round(s, 4)}
                        for nid, s in top]}
    if op == "registry":
        return {"ok": True, "registry": graph.to_structurelist(),
                "count": len(graph.to_structurelist())}
    return {"ok": False, "error": "bad_request",
            "message": f"unknown graph op {op!r}"}


# ══════════════════════════════════════════════════════════════════════════
# encoder — vector RAG over the encoder layer
# ══════════════════════════════════════════════════════════════════════════


def impl_encoder_op(args: dict) -> dict:
    """{op: search_nodes|search|ingest|save, query?, k?, ...}.
    An encoder passed IN the payload wins (per-agent instances);
    otherwise the bridge's current encoder is used."""
    from general_tools.construct import current_encoder
    encoder = args.get("encoder") or current_encoder()
    if encoder is None:
        return {"ok": False, "error": "no_encoder_bound",
                "message": "no encoder bound to the tools node"}
    graph = _graph()
    op = args.get("op")
    if op in ("search_nodes", "search"):
        query = str(args.get("query") or "")
        if not query:
            return {"ok": False, "error": "bad_request",
                    "message": "query required"}
        k = int(args.get("k") or 10)
        hits = encoder.search_nodes(query, k=k)
        nodes = []
        for nid, sim in hits:
            name = (graph.get_node(nid).entryname
                    if graph and graph.get_node(nid) else nid)
            nodes.append({"node_id": nid, "entryname": name,
                          "score": round(sim, 4)})
        chunks = []
        for chunk, sim in encoder.search(query, k=min(k, 8)):
            chunks.append({"chunk_id": chunk.chunk_id,
                           "section": getattr(chunk, "section", ""),
                           "text": chunk.text[:220],
                           "sim": round(sim, 4)})
        if op == "search_nodes":
            lines = [f"top-{len(hits)} nodes by vector similarity:"]
            for nid, sim in hits:
                name = (graph.get_node(nid).entryname
                        if graph and graph.get_node(nid) else nid)
                lines.append(f"  {name} [{nid}] sim={sim:.4f}")
            lines.append("top chunks:")
            for c in chunks[:8]:
                lines.append(f"  {c['chunk_id']} sim={c['sim']:.3f}: "
                             f"{c['text'][:80]}...")
            return {"ok": True, "content": "\n".join(lines),
                    "nodes": nodes, "chunks": chunks}
        return {"ok": True, "nodes": nodes, "chunks": chunks}
    if op == "ingest":
        nid = str(args.get("node_id") or "")
        text = str(args.get("text") or "")
        if not nid or not text:
            return {"ok": False, "error": "bad_request",
                    "message": "node_id and text required"}
        encoder.ingest_meta(nid, text)
        return {"ok": True, "node_id": nid}
    if op == "save":
        encoder.save()
        return {"ok": True}
    return {"ok": False, "error": "bad_request",
            "message": f"unknown encoder op {op!r}"}


# ══════════════════════════════════════════════════════════════════════════
# build — graph seeding / rebuild / export (the build scripts as ops)
# ══════════════════════════════════════════════════════════════════════════


def impl_build_op(args: dict) -> dict:
    """{op: build|cy3|export, out_dir?, topic?}."""
    op = args.get("op")
    if op == "build":
        from general_tools.build import build_graph
        g, enc = build_graph()
        g.pagerank()
        from general_tools.construct import bind_tools
        bind_tools(graph=g, encoder=enc)
        return {"ok": True, "nodes": len(g._nodes),
                "edges": len(g._edges),
                "chunks": enc.index.size() if enc.index else 0}
    if op == "cy3":
        from general_tools.build_cy3 import build_cy3_graph
        out_dir = args.get("out_dir")
        g, enc = build_cy3_graph(out_dir=Path(out_dir) if out_dir else None)
        from general_tools.construct import bind_tools
        bind_tools(graph=g, encoder=enc)
        return {"ok": True, "nodes": len(g._nodes),
                "edges": len(g._edges)}
    if op == "export":
        graph = _graph()
        if graph is None:
            return {"ok": False, "error": "no_graph_bound",
                    "message": "no graph bound to the tools node"}
        from general_tools.build import export_backward_compatible
        out = export_backward_compatible(graph)
        return {"ok": True, "path": str(out),
                "registry_entries": len(graph.to_structurelist()),
                "edge_files": len(graph.to_edges_files())}
    return {"ok": False, "error": "bad_request",
            "message": f"unknown build op {op!r}"}


# ══════════════════════════════════════════════════════════════════════════
# check — the read-only audit suite (review/standard/advanced)
# ══════════════════════════════════════════════════════════════════════════

SKIP_DIRS = {"__pycache__", ".git", ".vscode", "node_modules", "graph_data",
             "assets"}

THREAT_PATTERNS = [
    (r"(?i)sk-[a-zA-Z0-9]{20,}", "exposed API key (sk-…)"),
    (r"(?i)api[_-]?key\s*[=:]\s*['\"][^'\"]{8,}", "api key literal"),
    (r"(?i)password\s*[=:]\s*['\"][^'\"]{6,}", "password literal"),
    (r"(?i)secret\s*[=:]\s*['\"][^'\"]{8,}", "secret literal"),
    (r"(?i)token\s*[=:]\s*['\"][^'\"]{12,}", "token literal"),
    (r"(?i)\brm\s+-rf\s+/", "destructive rm"),
    (r"(?i)\beval\s*\(", "eval()"),
    (r"(?i)\bexec\s*\(", "exec()"),
    (r"(?i)subprocess\.(run|Popen|call)", "subprocess usage"),
    (r"(?i)pickle\.loads?", "unsafe pickle"),
    (r"(?i)sql\s*\+", "string-concatenated SQL"),
]


def _iter_files(root: Path,
                exts=(".py", ".js", ".ts", ".md", ".txt", ".json", ".html",
                      ".env", ".cfg")):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(exts) or fn in (".env",):
                yield Path(dp) / fn


def _check_root(args: dict) -> Path:
    return Path(str(args.get("workspace_root") or Config.WORKSPACE_ROOT))


def impl_check_op(args: dict) -> dict:
    """{op: review|standard|advanced, workspace_root?} — READ-ONLY audits."""
    op = args.get("op")
    root = _check_root(args)
    if op == "review":
        found: list[dict] = []
        for path in _iter_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat, label in THREAT_PATTERNS:
                for m in re.finditer(pat, text):
                    found.append({
                        "file": str(path.relative_to(root)),
                        "line": text[: m.start()].count("\n") + 1,
                        "threat": label,
                        "snippet": m.group(0)[:60],
                    })
                    break  # one per pattern per file
        found.sort(key=lambda x: (x["threat"], x["file"]))
        top = found[:15]
        lines = [f"top threats: {len(found)} candidate(s) found", ""]
        for t in top:
            lines.append(f"  ⚠ {t['threat']} — {t['file']}:{t['line']}  "
                         f"{t['snippet']!r}")
        if not top:
            lines.append("  (none detected)")
        return {"ok": True, "content": "\n".join(lines), "count": len(found)}
    if op == "standard":
        checks: list[str] = []
        problems: list[str] = []
        for req in ("README.md", "requirements.txt", "LICENSE"):
            if (root / req).exists():
                checks.append(f"✓ {req} present")
            else:
                problems.append(f"✗ missing {req}")
        syn_errs = 0
        for path in _iter_files(root, exts=(".py",)):
            try:
                compile(path.read_text(encoding="utf-8", errors="ignore"),
                        str(path), "exec")
            except (SyntaxError, OSError):
                syn_errs += 1
                problems.append(f"✗ syntax error in {path.relative_to(root)}")
        checks.append(f"✓ python files compiled ({syn_errs} syntax errors)")
        graph = _graph()
        if graph is not None:
            viol = len(graph.validate_consistency())
            checks.append(f"✓ graph: {len(graph._nodes)} nodes, "
                          f"{len(graph._edges)} edges, {viol} violations")
            if viol:
                problems.append(f"✗ {viol} graph consistency violations")
        else:
            checks.append("· graph not bound — skipping consistency")
        return {"ok": True,
                "content": "\n".join(checks + (["", "PROBLEMS:"] + problems
                                               if problems else
                                               ["", "all standard checks "
                                                     "passed"]))}
    if op == "advanced":
        lines: list[str] = ["advanced audit"]
        big = []
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                p = Path(dp) / fn
                try:
                    if p.stat().st_size > 2_000_000:
                        big.append(f"{p.relative_to(root)} "
                                   f"({p.stat().st_size / 1e6:.1f} MB)")
                except OSError:
                    pass
        lines.append(f"large files (>2MB): {len(big)}" +
                     (":\n  " + "\n  ".join(big[:8]) if big else ""))
        envs = list(root.rglob(".env"))
        lines.append(f".env files: {len(envs)}")
        for e in envs[:4]:
            rel = e.relative_to(root)
            lines.append(f"  · {rel} "
                         f"{'⚠ in repo' if '.git' not in str(e) else ''}")
        todo = 0
        for p in _iter_files(root, exts=(".py", ".js", ".md")):
            try:
                todo += len(re.findall(
                    r"(?i)\b(TODO|FIXME|HACK)\b",
                    p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
        lines.append(f"TODO/FIXME markers: {todo}")
        req = root / "requirements.txt"
        if req.exists():
            unpinned = [ln.strip().split("#")[0].strip()
                        for ln in req.read_text(encoding="utf-8").splitlines()
                        if ln.strip() and not ln.strip().startswith("#") and
                        ">=" not in ln and "==" not in ln]
            lines.append(f"requirements: {len(unpinned)} unpinned entries")
        return {"ok": True, "content": "\n".join(lines)}
    return {"ok": False, "error": "bad_request",
            "message": f"unknown check op {op!r}"}
