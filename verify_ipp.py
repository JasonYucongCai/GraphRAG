"""
Full IPP v0.2.8 verification: construct every node, run live pipelines,
check the 17 invariants + audit hash chains on every node.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent
sys.path.insert(0, str(WS))

from general_tools.IPP_runtime import verify_node, verify_all  # noqa: E402

# bootstrap the shared tools node (Γ builds the F-file catalog — there is
# no legacy BaseTool/ToolRegistry layer to register anymore)
from general_tools.construct import tools_node  # noqa: E402
tools_node()


def _raises(fn):
    try:
        fn()
        return False
    except Exception:  # noqa: BLE001
        return True


def check(name, cond):
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    return cond


ok_all = True

# ═══════════════════════════════════════════════════════════════════════
# 1. LLM node (user API: from LLMs.IPP import llm_node)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 1. LLM node ===")
from LLMs.IPP import llm_node  # noqa: E402

node = llm_node()
ok_all &= check("constructed", node.node_id == "llm")
r = node.invoke("chat", [{"role": "user", "content": "Reply with OK only"}])
ok_all &= check("live chat", r.payload and "OK" in str(r.payload["content"]))
r2 = node.invoke("complete", {"system": "", "user": "Reply: OK"})
ok_all &= check("complete", bool(r2.payload))
gen = node.invoke("chat_stream", [{"role": "user", "content": "Reply: OK"}])
ok_all &= check("chat_stream", len(gen.payload["events"]) > 0)
for ch in node.channels:
    ok_all &= check(f"audit chain {ch}", node.executors[ch].audit_verify())
fails = verify_node(node)
ok_all &= check("LLM node ALL 17 OK", not fails)
if fails:
    print("   failures:", fails)

# ═══════════════════════════════════════════════════════════════════════
# 2. codex_growth agent (engine + tools + llm nodes via Γ)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 2. codex_growth ===")
from general_tools.build import build_graph  # noqa: E402

graph, encoder = build_graph()
from codex_growth import create_agent as mk_growth  # noqa: E402

g_engine = mk_growth(graph, encoder)
ok_all &= check("engine.node attached", g_engine.node is not None)
ok_all &= check("tools node built", g_engine._tools_node.node_id ==
                "codex_growth_tools")
print(g_engine.node.summary())

# tools node: list + describe + invoke (current_time is in the shared suite)
agent_tools_node = g_engine._tools_node
tl = agent_tools_node.invoke("list", None)
ok_all &= check("tools list", len(tl.payload) > 10)
td = agent_tools_node.invoke("describe", {"tool": tl.payload[0]})
ok_all &= check("tools describe", td.payload is not None)
try:
    ti = agent_tools_node.invoke("invoke", {"tool": "current_time",
                                             "args": {}})
    ok_all &= check("tools invoke", ti.payload.get("ok") is not False)
except Exception as exc:  # noqa: BLE001
    ok_all &= check(f"tools invoke ({exc})", False)

# engine node: internal pipeline ground → chat (blocking internal edge)
pipe = g_engine.node.invoke(
    "ground", {"task": "Reply with OK only", "node_id": "agent_memory"})
ok_all &= check("internal pipeline ground→chat",
                "OK" in str(pipe.payload.get("answer", ""))[:200])
last = g_engine.node.executors["chat"].audit_log[-1]
ok_all &= check("internal traversal audited (source=internal)",
                last.get("source") == "internal"
                and last.get("source_channel") == "ground")
ok_all &= check("ground channel audited", len(
    g_engine.node.executors["ground"].audit_log) >= 1)
for n in (g_engine.node, g_engine._tools_node):
    fails = verify_node(n)
    ok_all &= check(f"{n.node_id} ALL 17 OK", not fails)
    if fails:
        print("   failures:", fails)

# ═══════════════════════════════════════════════════════════════════════
# 3. codex_RAG agent
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 3. codex_RAG ===")
from codex_RAG import create_agent as mk_rag  # noqa: E402

r_engine = mk_rag(graph, encoder)
ok_all &= check("engine.node attached", r_engine.node is not None)
res = r_engine.node.invoke(
    "ground", {"task": "List the retrieval techniques. Reply with OK only.",
               "node_id": "g_retrieval"})
ok_all &= check("RAG internal pipeline", "OK" in
                str(res.payload.get("answer", ""))[:200])
for n in (r_engine.node, r_engine._tools_node):
    fails = verify_node(n)
    ok_all &= check(f"{n.node_id} ALL 17 OK", not fails)
    if fails:
        print("   failures:", fails)

# ═══════════════════════════════════════════════════════════════════════
# 4. codex_normal agent
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 4. codex_normal ===")
from codex_normal import create_agent as mk_normal  # noqa: E402

n_engine = mk_normal(graph, encoder)
ok_all &= check("engine.node attached", n_engine.node is not None)
res = n_engine.node.invoke(
    "ground", {"task": "Reply with OK only", "node_id": "grag_framework"})
ok_all &= check("normal internal pipeline", "OK" in
                str(res.payload.get("answer", ""))[:200])
for n in (n_engine.node, n_engine._tools_node):
    fails = verify_node(n)
    ok_all &= check(f"{n.node_id} ALL 17 OK", not fails)
    if fails:
        print("   failures:", fails)

# ═══════════════════════════════════════════════════════════════════════
# 5. topology resolution: engine executors have resolved partners
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 5. external topology (constructor-resolved) ===")
ctx = g_engine._ipp_context
print("  registry:", sorted(ctx.registry.keys()))
chat_ex = g_engine.node.executors["chat"]
ok_all &= check("chat upstream = llm resolved",
                any(u[0] == "llm" for u in chat_ex.upstream))
ok_all &= check("chat downstream = tools resolved",
                any(d[0] == "codex_growth_tools" for d in chat_ex.downstream))
ok_all &= check("X6: set_topology forbidden",
                _raises(g_engine.node.executors["chat"].set_topology))

# ═══════════════════════════════════════════════════════════════════════
# 6. database node — the note store as an IPP component (isolated store)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 6. database node (the note store as an IPP component) ===")
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from database.notes import NoteStore  # noqa: E402
from general_tools.graph import KnowledgeGraph  # noqa: E402
from database.construct import (  # noqa: E402
    reset_database_node, bind_database, database_node,
)

db_store = NoteStore(root=Path(tempfile.mkdtemp(prefix="ipp-db-verify-")))
db_graph = KnowledgeGraph(auto_load=False)
reset_database_node()
bind_database(store=db_store, graph=db_graph)
db_node = database_node()
ok_all &= check("constructed", db_node.node_id == "database" and
                len(db_node.channels) == 6)
ok_all &= check("channels",
                set(db_node.channels) ==
                {"project", "nodes", "edges", "graph", "supplement",
                 "categories"})

r = db_node.invoke("project", {"op": "create", "name": "Verify Project",
                               "description": "verify_IPP"}).payload
ok_all &= check("create_project via envelope", r.get("ok"))
r = db_node.invoke("project", {"op": "list"}).payload
ok_all &= check("list_projects via envelope", r.get("ok") and
                len(r.get("projects", [])) == 1)
r = db_node.invoke("nodes", {"op": "register", "node_id": "v1",
                             "entryname": "Verify Node",
                             "category": "concept"}).payload
ok_all &= check("register_node via envelope", r.get("ok"))
r = db_node.invoke("nodes", {"op": "register", "node_id": "v2",
                             "entryname": "Verify Node 2"}).payload
r = db_node.invoke("edges", {"op": "link", "source": "v1", "target": "v2",
                             "relation": "cites"}).payload
ok_all &= check("link_nodes via envelope", bool(r.get("ok") and r.get("edge_id")))
r = db_node.invoke("graph", {"op": "sync"}).payload
ok_all &= check("sync_project via envelope", bool(r.get("ok") and
                r.get("created", 0) + r.get("updated", 0) >= 2))
r = db_node.invoke("nodes", {"op": "get_note", "node_id": "v1"}).payload
ok_all &= check("get_note via envelope", r.get("ok"))
r = db_node.invoke("nodes", {"op": "get_note", "node_id": "nope"}).payload
ok_all &= check("missing note → structured error", not r.get("ok") and
                r.get("error") == "not_found")
r = db_node.invoke("categories", {"op": "update",
                                  "map": {"concept": "#123456"}}).payload
ok_all &= check("update_categories via envelope", r.get("ok"))
r = db_node.invoke("supplement", {"op": "create", "name": "Bundle",
                                  "project": "verify_project"}).payload
ok_all &= check("create_supplement via envelope", r.get("ok"))
fails = verify_node(db_node)
ok_all &= check("database node ALL 17 OK", not fails)
if fails:
    print("   failures:", fails)
ok_all &= check("database audit chains verify",
                all(ex.audit_verify() for ex in db_node.executors.values()))
aud = db_node.executors["nodes"].audit_log[-1]
ok_all &= check("audit records carry op + project",
                aud.get("op") == "get_note" and aud.get("project") ==
                "verify_project")

# 6b. the STRICT chain: tools node invoke → router → database node envelope
r = tools_node().invoke(
    "invoke", {"tool": "register_node",
               "args": {"node_id": "v3", "entryname": "Facade Node",
                         "category": "note"},
               "graph": db_graph}).payload
ok_all &= check("router executes register_node through the database node",
                bool(r.get("ok")))
ok_all &= check("router hop audited on the tools invoke channel",
                tools_node().executors["invoke"].audit_log[-1].get("tool") ==
                "register_node")
ok_all &= check("target hop audited on the database nodes channel",
                db_node.executors["nodes"].audit_log[-1].get("op") ==
                "register")

# ═══════════════════════════════════════════════════════════════════════
# 7. tools node — the SHARED runtime as an IPP component (isolated ctx)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== 7. tools node (the SHARED runtime as an IPP component) ===")
from general_tools.construct import (  # noqa: E402
    reset_tools_node, bind_tools, tools_node,
)
from general_tools.graph import KnowledgeGraph as _KG  # noqa: E402
from general_tools.encoder import EncoderLayer  # noqa: E402

t_graph = KnowledgeGraph(auto_load=False)
t_enc = EncoderLayer()
reset_tools_node()
bind_tools(graph=t_graph, encoder=t_enc)
tools = tools_node()
ok_all &= check("constructed", tools.node_id == "tools" and
                len(tools.channels) == 26)
ok_all &= check("channels include the 19 codex channels",
                {"read_file", "shell_command", "web_search",
                 "current_time"} <= set(tools.channels))
ok_all &= check("catalog built from the F-files",
                len(tools.constructor.context.bindings.get(
                    "tools_catalog", {})) >= 50)

r = tools.invoke("list", {"names": ["get_local_graph", "register_node",
                                    "current_time"]}).payload
ok_all &= check("list definitions via envelope",
                bool(r.get("ok")) and len(r.get("definitions", [])) == 3)
r = tools.invoke("invoke", {"tool": "current_time"}).payload
ok_all &= check("flat tool via envelope",
                bool(r.get("ok")) and bool(r.get("content")))
r = tools.invoke("invoke", {"tool": "unknown_tool_xyz"}).payload
ok_all &= check("unknown tool → structured error",
                not r.get("ok") and r.get("error") == "unknown_tool")
r = tools.invoke("graph", {"op": "stats"}).payload
ok_all &= check("graph op via envelope", bool(r.get("ok")) and
                r.get("nodes") == 0)
r = tools.invoke("encoder", {"op": "search", "query": "x", "k": 3}).payload
ok_all &= check("encoder op via envelope", bool(r.get("ok")))
r = tools.invoke("check", {"op": "standard"}).payload
ok_all &= check("check op via envelope", bool(r.get("ok")))
fails = verify_node(tools)
ok_all &= check("tools node ALL 17 OK", not fails)
if fails:
    print("   failures:", fails)
ok_all &= check("tools audit chains verify",
                all(ex.audit_verify() for ex in tools.executors.values()))
inv_audits = [rec for rec in tools.executors["invoke"].audit_log
              if rec.get("tool") == "current_time"]
ok_all &= check("audit records carry tool",
                bool(inv_audits) and inv_audits[0].get("op") == "")
# a codex channel has its OWN envelope + audit (per-tool logs)
r = tools.invoke("current_time", {}).payload
ok_all &= check("codex channel via its own envelope",
                bool(r.get("ok")) and bool(r.get("content")))
ok_all &= check("codex channel audited separately",
                len(tools.executors["current_time"].audit_log) >= 1 and
                tools.executors["current_time"].audit_verify())
# the router rejects unknown routes with a structured error
r = tools.invoke("invoke", {"tool": "no_such_tool"}).payload
ok_all &= check("unknown tool → structured error",
                not r.get("ok") and r.get("error") == "unknown_tool")
# the catalog derives exact definitions from the F-files
r = tools.invoke("list", {"names": ["register_node", "read_file"]}).payload
ok_all &= check("catalog definitions from the F-files",
                bool(r.get("ok")) and len(r.get("definitions", [])) == 2 and
                r["definitions"][0]["function"]["name"] == "register_node")

print("\n" + ("═══ ALL IPP VERIFICATIONS PASSED ═══" if ok_all
              else "═══ SOME CHECKS FAILED ═══"))
