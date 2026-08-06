"""
Full IPP v0.2.8 verification: construct every node, run live pipelines,
check the 17 invariants + audit hash chains on every node.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent
sys.path.insert(0, str(WS))

from tools.IPP_runtime import verify_node, verify_all  # noqa: E402
from tools.graph_tools import ensure_tools  # noqa: E402

ensure_tools()


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
from tools.build import build_graph  # noqa: E402

graph, encoder = build_graph()
from codex_growth import create_agent as mk_growth  # noqa: E402

g_engine = mk_growth(graph, encoder)
ok_all &= check("engine.node attached", g_engine.node is not None)
ok_all &= check("tools node built", g_engine._tools_node.node_id ==
                "codex_growth_tools")
print(g_engine.node.summary())

# tools node: list + describe + invoke (current_time is in the shared suite)
tools_node = g_engine._tools_node
tl = tools_node.invoke("list", None)
ok_all &= check("tools list", len(tl.payload) > 10)
td = tools_node.invoke("describe", {"tool": tl.payload[0]})
ok_all &= check("tools describe", td.payload is not None)
try:
    ti = tools_node.invoke("invoke", {"tool": "current_time", "args": {}})
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

print("\n" + ("═══ ALL IPP VERIFICATIONS PASSED ═══" if ok_all
              else "═══ SOME CHECKS FAILED ═══"))
