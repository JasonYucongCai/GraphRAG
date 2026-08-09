"""Server smoke test: the /api/database/* endpoints now flow through the
database IPP node's guardrail envelopes. Uses the Flask test client
(no ports). Creates a TEMP project, exercises the endpoints, then cleans
up and restores the previously active project."""
import shutil
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))

from general_tools.config import Config  # noqa: E402
from database.construct import current_store as db_current_store  # noqa: E402
import ui.server as srv  # noqa: E402

DB = Config.WORKSPACE_ROOT / "database"
PROJ = "zz-ipp-verify"
failures = []


def check(name, cond):
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


print("=== 0. server startup (loads the active project + database node) ===")
srv._load_or_build(None)
check("store bound", srv.store is not None and srv.store.current() is not None)
node = srv.database_node()
check("database node constructed", node.node_id == "database" and
      len(node.channels) == 6)
check("database node bound to the server store",
      db_current_store() is srv.store)

client = srv.app.test_client()

print("\n=== 1. project lifecycle via the node ===")
r = client.get("/api/database/projects")
j = r.get_json()
check("GET projects", r.status_code == 200 and "projects" in j and
      "current" in j)
check("current project = active", j["current"] == srv.store.current())

r = client.post("/api/database/create", json={"name": PROJ,
                                              "description": "smoke test"})
j = r.get_json()
check("POST create", r.status_code == 200 and j.get("ok") and
      j["project"]["slug"] == PROJ)

r = client.post("/api/database/open", json={"name": PROJ, "replace": True})
j = r.get_json()
check("POST open", r.status_code == 200 and j.get("ok") and
      j.get("project", {}).get("slug") == PROJ)

r = client.get("/api/database/projects")
j = r.get_json()
check("current switched", j["current"] == PROJ)

print("\n=== 2. notes + sync via the node ===")
r = client.get("/api/database/notes")
j = r.get_json()
check("GET notes (empty project)", r.status_code == 200 and
      j["notes"] == [] and j["project"] == PROJ)

r = client.post("/api/database/sync", json={})
j = r.get_json()
check("POST sync", r.status_code == 200 and j.get("ok"))

r = client.get("/api/database/note/zz-missing")
check("GET note missing → 404", r.status_code == 404)

r = client.post("/api/database/note/update",
                json={"node_id": "zz-missing"})
check("POST note update missing → 404", r.status_code == 404)

print("\n=== 3. categories + supplements via the node ===")
r = client.get("/api/database/categories")
j = r.get_json()
check("GET categories", r.status_code == 200 and "map" in j and
      j["project"] == PROJ)

r = client.post("/api/database/categories",
                json={"map": {"subject": "#ff00ff"}, "default": "#abcdef"})
j = r.get_json()
check("POST categories", r.status_code == 200 and j.get("ok") and
      j["map"].get("subject") == "#ff00ff" and j["default"] == "#abcdef")

r = client.get("/api/database/categories?project=china-economic-structure")
j = r.get_json()
check("GET categories scoped", r.status_code == 200 and
      j["project"] == "china-economic-structure")

r = client.get("/api/database/supplements")
j = r.get_json()
check("GET supplements (empty)", r.status_code == 200 and
      j["supplements"] == [])

r = client.post("/api/database/supplement/create",
                json={"name": "zz-bundle"})
j = r.get_json()
check("POST supplement create", r.status_code == 200 and j.get("ok"))

r = client.get("/api/database/supplements")
j = r.get_json()
check("GET supplements (1 bundle)", r.status_code == 200 and
      len(j["supplements"]) == 1)

print("\n=== 4. database node audit trail from the UI calls ===")
aud = {ch: len(ex.audit_log) for ch, ex in node.executors.items()}
print("   audit records:", aud)
check("project channel audited", aud.get("project", 0) >= 4)
check("categories channel audited", aud.get("categories", 0) >= 3)
check("supplement channel audited", aud.get("supplement", 0) >= 2)
check("audit chains verify",
      all(ex.audit_verify() for ex in node.executors.values()))

print("\n=== 4b. tools node — /api/search through the encoder channel ===")
from general_tools.construct import tools_node as shared_tools_node
tnode = shared_tools_node()
check("tools node constructed", tnode.node_id == "tools" and
      len(tnode.channels) == 26)
r = client.post("/api/search", json={"query": "graph", "k": 3})
j = r.get_json()
check("POST /api/search", r.status_code == 200 and "nodes" in j and
      "chunks" in j)
check("tools encoder channel audited",
      len(tnode.executors["encoder"].audit_log) >= 1)
check("tools audit chains verify",
      all(ex.audit_verify() for ex in tnode.executors.values()))

print("\n=== 5. cleanup: restore the previously active project ===")
prev = "china-economic-structure"
srv.store.open_project(prev)
check("previous project restored", srv.store.current() == prev)
proj_dir = DB / PROJ
if proj_dir.exists():
    shutil.rmtree(proj_dir)
    check("temp project removed", not proj_dir.exists())
else:
    check("temp project removed", True)

print("\n" + ("SERVER SMOKE PASSED" if not failures else
              f"SERVER SMOKE FAILED: {failures}"))
sys.exit(0 if not failures else 1)
