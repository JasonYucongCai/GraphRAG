"""
social_activity.demo — end-to-end verification of the plug-and-play
social_activity component.

Run:  python -m IPP_Social.IPP_Social_services_tools.IPP_Social_services_demo [--keep]

Uses a throwaway database (``IPP_Social/demo_db/``) so the real
``social_database/`` and the ``agents/dataset/`` are untouched.

Covers: 17 invariants, agent registration, ManyAgents provisioning,
Agent Card discovery + cross-agent comments, the three agent properties
(capacity / random property / constraints with physical validation),
shared goal-task folders (Markdown tasks with VCL), the global chat
board, push notifications (chat-board scoped), the streaming event bus
(buffered + live), and the four formal A2A modes (sync disabled,
async + stream enabled, push scoped).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
if str(WS) not in sys.path:
    sys.path.insert(0, str(WS))

from IPP_Social.social_activity import SocialActivity  # noqa: E402
from IPP_Social.IPP_Social_services_tools.IPP_Social_services_provision import (  # noqa: E402
    provision_many_agents,
)
from IPP.IPP_verify import verify_node  # noqa: E402

DEMO_DB = Path(__file__).resolve().parents[1] / "demo_db"
DEMO_DATASET = DEMO_DB / "agents_dataset"


def check(name: str, cond: bool) -> bool:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    return cond


def run_demo(db_root: Path | str | None = None,
             dataset_root: Path | str | None = None,
             fresh: bool = True) -> int:
    db = Path(db_root) if db_root else DEMO_DB
    ds = Path(dataset_root) if dataset_root else DEMO_DATASET
    if fresh and db.exists():
        shutil.rmtree(db)

    ok_all = True
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  social_activity — plug-and-play IPP v0.2.8 social component  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"\ndatabase root: {db}\ndataset root:  {ds}")

    # ══ 0. construct the node — ALL 17 invariants ═══════════════════════
    print("\n=== 0. Construct + 17 invariants ===")
    social = SocialActivity(db_root=db, dataset_root=ds)
    node = social.node
    print(node.summary())
    fails = verify_node(node)
    ok_all &= check(f"ALL 17 invariants OK ({len(fails)} failures)", not fails)
    if fails:
        print("   failures:", fails)

    # ══ 1. registration (3 manual agents) ════════════════════════════════
    print("\n=== 1. Agent registration (capacity / random / constraints) ===")
    ruby = {
        "math": 78, "physics": 65, "engineering": 82, "biology": 40,
        "genomics": 35, "reasoning": 80, "research": 70, "social": 74,
        "play": 72, "creativity": 76,
    }
    alice = {d: 68 for d in ("math", "physics", "engineering")}
    r = social.register_agent(
        "Codex_16_Ruby", "Ruby",
        capacity=ruby,
        random_property={d: {"mean": ruby[d] - 2, "variance": 9}
                         for d in ruby},
        constraints={"position": {"x": 10, "y": 20, "z": 5}},
        bio="bold, dynamic, decisive")
    ok_all &= check("Ruby registered", r.get("ok") and
                    r["card"]["capacity"]["engineering"] == 82)
    r = social.register_agent(
        "Codex_01_Alice", "Alice", capacity=alice,
        bio="proactive coordinator")
    ok_all &= check("Alice registered (partial capacity auto-filled)",
                    r.get("ok") and
                    r["card"]["capacity"]["genomics"] == 50)
    dup = social.register_agent("Codex_01_Alice", "Alice")
    ok_all &= check("duplicate registration rejected", not dup.get("ok"))
    ok_all &= check("Ruby card persisted as JSON dataset file",
                    (ds / "Codex_16_Ruby.json").exists())

    # ══ 2. provision the 20 ManyAgents ═══════════════════════════════════
    print("\n=== 2. Connect ManyAgents (20 Codex agents) ===")
    registered = provision_many_agents(social.dataset)
    # Alice + Ruby were registered manually in section 1 — provisioner
    # skips existing cards, so 18 of the 20 Codex folders are new.
    ok_all &= check(f"provisioned {len(registered)}/20 agents "
                    "(2 already registered manually)",
                    len(registered) == 18)
    ok_all &= check("dataset folder now holds 20 JSON files",
                    len(social.dataset.dataset_files()) == 20)
    disc = social.discover()
    ok_all &= check(f"total cards discoverable = {len(disc['cards'])}",
                    len(disc["cards"]) == 20)
    ruby_card = next(c for c in disc["cards"]
                     if c["agent_id"] == "Codex_16_Ruby")
    ok_all &= check("Ruby card has 10-dim capacity",
                    len(ruby_card["capacity"]) == 10)
    ok_all &= check("Ruby card has 10-dim random property",
                    len(ruby_card["random_property"]) == 10)
    ok_all &= check("Ruby card has physical constraints",
                    set(ruby_card["constraints"]["position"]) ==
                    {"x", "y", "z"})

    # ══ 3. Agent Card — discovery + cross-agent comments ═════════════════
    print("\n=== 3. Agent Card (discovery + comments by others) ===")
    c = social.comment_card("Codex_01_Alice", "Codex_16_Ruby",
                            "Great coordinator — pushed the CY3 review fast!")
    ok_all &= check("Ruby commented on Alice's card",
                    c.get("ok") and
                    c["card"]["comments"][-1]["author_id"] == "Codex_16_Ruby")
    ok_all &= check("card version bumped by comment",
                    c["card"]["version"] == 2)
    c = social.comment_card("Codex_16_Ruby", "Codex_01_Alice",
                            "Bold energy — lively, never reckless.")
    ok_all &= check("Alice annotated Ruby's card back", c.get("ok"))
    unknown = social.comment_card("nobody", "Codex_16_Ruby", "hi")
    ok_all &= check("comment on unknown agent rejected",
                    unknown.get("error") == "unknown_agent")

    # ══ 4. The three properties ══════════════════════════════════════════
    print("\n=== 4. Profile: capacity / random property / constraints ===")
    p = social.get_profile("Codex_16_Ruby")
    ok_all &= check("profile has all three properties",
                    {"capacity", "random_property", "constraints"} <= set(p))
    sample = social.dataset.load_card("Codex_16_Ruby").random_property.sample(
        seed=42)
    ok_all &= check("random property samples a 10-dim mention vector",
                    len(sample) == 10 and
                    all(0.0 <= v <= 100.0 for v in sample.values()))
    moved = social.update_constraints("Codex_01_Alice",
                                      position={"x": 5, "y": 5})
    ok_all &= check("constraints moved within step limit",
                    moved.get("ok") and moved["constraints"]["position"] ==
                    {"x": 5.0, "y": 5.0, "z": 0.0})
    tele = social.update_constraints("Codex_01_Alice", position={"x": 90})
    ok_all &= check("teleport rejected (max step)",
                    tele.get("error") == "constraint_violation")
    neg = social.update_constraints("Codex_01_Alice", resources={"energy": -5})
    ok_all &= check("negative resource rejected",
                    neg.get("error") == "constraint_violation")
    bounds = social.update_constraints("Codex_01_Alice", position={"z": 500})
    ok_all &= check("out-of-world position rejected",
                    bounds.get("error") == "constraint_violation")

    # ══ 5. Shared task management (goal folder + task .md files) ═════════
    print("\n=== 5. Shared task management (goal folder, md tasks) ===")
    g = social.create_goal("Calabi-Yau Survey",
                           description="Survey CY3 polytope multiplicities",
                           owner_agent_id="Codex_01_Alice")
    goal_id = g["goal"]["goal_id"]
    ok_all &= check(f"goal created: {goal_id}", g.get("ok"))
    t = social.create_task(goal_id, "Review polytope multiplicities",
                           description="Check the 17/28/66/81 special verdicts",
                           assignee_agent_id="Codex_16_Ruby",
                           author_agent_id="Codex_01_Alice")
    task_id = t["task"]["task_id"]
    ok_all &= check(f"task created: {task_id}", t.get("ok"))
    u = social.update_task(goal_id, task_id, "Codex_16_Ruby",
                           status="processing",
                           note="pulled the KS-gap table, diagonal contiguous 14..99")
    ok_all &= check("Ruby updated task → processing", u.get("ok") and
                    u["task"]["status"] == "processing")
    u = social.update_task(goal_id, task_id, "Codex_01_Alice",
                           status="completed",
                           note="verdicts confirmed by Alice")
    ok_all &= check("Alice completed the task (collaboration)",
                    u.get("ok") and u["task"]["status"] == "completed")
    task_file = db / "goals" / goal_id / "tasks" / f"{task_id}.md"
    ok_all &= check("task exists as a Markdown file", task_file.exists())
    body = task_file.read_text(encoding="utf-8")
    ok_all &= check("task md has Version Control Log at the bottom",
                    "## Version Control Log" in body and
                    "Ruby" in body and "Alice" in body)
    gt = social.get_task(goal_id, task_id)
    ok_all &= check("get_task returns notes + VCL",
                    len(gt["notes"]) == 2 and len(gt["vcl"]) == 3)
    lt = social.list_tasks(goal_id, status="completed")
    ok_all &= check("list_tasks filters by status", len(lt["tasks"]) == 1)

    # ══ 6. Global chat board ═════════════════════════════════════════════
    print("\n=== 6. Global chat board ===")
    m = social.post_message("Codex_16_Ruby",
                            "Survey goal open — volunteers welcome!",
                            tags=["announcement"])
    ok_all &= check("Ruby posted to the board", m.get("ok") and
                    m["message"]["message_id"] == 1)
    m2 = social.post_message("Codex_01_Alice", "Ruby, thanks for the KS table!")
    ok_all &= check("Alice replied", m2.get("ok"))
    msgs = social.get_messages_since(after_id=1)
    ok_all &= check("get_since returns only newer messages",
                    len(msgs["messages"]) == 1 and
                    msgs["messages"][0]["author_agent_id"] == "Codex_01_Alice")

    # ══ 7. A2A modes: async / stream / push / sync ═══════════════════════
    print("\n=== 7. A2A formal methods ===")
    h = social.a2a_async_submit("Codex_01_Alice", goal_id,
                                "Please double-check the self-mirror diagonal",
                                title="Self-mirror check",
                                to_agent_id="Codex_16_Ruby")
    ok_all &= check("a2a async submit → task created",
                    h.get("ok") and h["mode"] == "async" and
                    h["status"] == "processing")
    st = social.a2a_async_status("Codex_16_Ruby", goal_id, h["task_id"])
    ok_all &= check("a2a async poll responds with current status",
                    st.get("ok") and "processing" in st["response"])
    s = social.a2a("sync", from_agent_id="Codex_01_Alice",
                   to_agent_id="Codex_16_Ruby", message="handoff?")
    ok_all &= check("a2a sync declared but NOT allowed",
                    s.get("error") == "mode_not_allowed" and
                    s.get("declared") is True and s.get("allowed") is False)
    ev = social.a2a("stream", since=0)
    ok_all &= check("a2a stream buffered events",
                    ev.get("mode") == "stream" and len(ev["events"]) > 10)
    psub = social.a2a_push_subscribe("Codex_01_Alice")
    ok_all &= check("a2a push subscribe (chat board)",
                    psub.get("ok") and psub["target"] == "chat_board")
    denied = social.a2a("push", action="subscribe", agent_id="Codex_01_Alice",
                        target="agents")
    ok_all &= check("a2a push outside chat board rejected",
                    denied.get("error") == "push_scope_denied")
    m3 = social.post_message("Codex_16_Ruby", "PUSH TEST — Ruby to the world")
    inbox = social.a2a_push_inbox("Codex_01_Alice")
    pushed = [n for n in inbox["inbox"]
              if n.get("message_id") == m3["message"]["message_id"]]
    ok_all &= check("chat board post pushed to subscriber inbox",
                    len(pushed) == 1 and
                    pushed[0]["kind"] == "chat_board_push")

    # ══ 8. Streaming event bus ═══════════════════════════════════════════
    print("\n=== 8. Streaming event bus (buffered + live) ===")
    stream = social.stream_events(since=0)
    ok_all &= check("buffered stream returns events + cursor",
                    stream["ok"] and len(stream["events"]) > 0 and
                    stream["cursor"] >= len(stream["events"]))
    live = social.stream_events(since=0, live=True, timeout_s=1.2)
    collected = [e for e in live]
    ok_all &= check("live stream yields events then ends (timeout)",
                    len(collected) > 0)

    # ══ 9. Audit chains + re-verify ══════════════════════════════════════
    print("\n=== 9. Audit + invariants (final) ===")
    ok_all &= check("all channel audit hash chains verify", social.audit_ok())
    fails = verify_node(node)
    ok_all &= check("ALL 17 invariants still OK", not fails)
    if fails:
        print("   failures:", fails)
    for ch in node.channels:
        rec = node.executors[ch].audit_log
        if rec:
            last = rec[-1]
            print(f"  audit[{ch}]: {len(rec)} records, "
                  f"last_seq={last.get('seq')}, "
                  f"op={last.get('social_op', '-')}, "
                  f"mode={last.get('social_mode', '-')}")

    print("\n" + ("✅ ALL CHECKS PASSED" if ok_all else "❌ SOME CHECKS FAILED"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="social_activity demo")
    ap.add_argument("--keep", action="store_true",
                    help="do not wipe the demo database first")
    args = ap.parse_args()
    sys.exit(run_demo(fresh=not args.keep))
