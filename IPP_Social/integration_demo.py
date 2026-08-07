"""
IPP_Social.integration_demo — headless verification of the full Multi Agent
platform (strict IPP v0.2.8).

Run:  python -m IPP_Social.integration_demo [--live]

Covers: one shared GraphContext 𝒢 (43 nodes), constructor-resolved portal
topology (social + 20 engine channels), 17 invariants on portal/social/llm
and sampled agent nodes, and a mini swarm run (2 agents) with the offline
MockProvider (or real DeepSeek with --live).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
if str(WS) not in sys.path:
    sys.path.insert(0, str(WS))

from tools.build import build_graph  # noqa: E402
from LLMs.deepseek import MockProvider  # noqa: E402
from IPP_Social.integration import build_platform, verify_platform  # noqa: E402


def check(name: str, cond: bool) -> bool:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    return cond


def run(use_live: bool = False) -> int:
    ok_all = True
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Multi Agent platform — strict IPP v0.2.8 integration demo    ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    graph, encoder = build_graph()
    provider = None if use_live else MockProvider()

    print("\n=== 0. Platform assembly (one GraphContext 𝒢) ===")
    platform = build_platform(graph, encoder, provider, store=None,
                              agent_chat_mode=True, max_concurrent=2)
    ctx = platform["ctx"]
    ok_all &= check(f"registry holds 43 nodes (got {len(ctx.registry)})",
                    len(ctx.registry) == 43)
    ok_all &= check("portal swarm topology = 40 engine channels",
                    len(platform["portal_node"].executors["swarm"]
                        .downstream) == 40)
    # SocialOp-in channels of social_activity: card/profile/tasks/chat_board
    # (a2a + events declare different input logical types)
    ok_all &= check("portal command topology = 4 social channels",
                    len(platform["portal_node"].executors["command"]
                        .downstream) == 4)
    ok_all &= check("20 runtimes assembled",
                    len(platform["runtimes"]) == 20)

    print("\n=== 1. 17 invariants (portal, social, llm, sample agents) ===")
    fails = verify_platform(platform, sample_agents=2)
    ok_all &= check(f"all nodes ALL 17 OK ({len(fails)} failures)", not fails)
    if fails:
        print("   failures:", fails)

    print("\n=== 2. Mini swarm (2 agents, goal → tasks → completion) ===")
    portal = platform["portal_node"]
    r = portal.invoke("swarm", {
        "op": "start", "goal": "Integration Demo",
        "instructions": "Reply with one word: OK.",
        "agent_ids": ["Codex_01_Alice", "Codex_16_Ruby"]}).payload
    ok_all &= check(f"swarm started (goal={r.get('goal_id')}, "
                    f"{len(r.get('agents', []))} agents)", r.get("ok"))
    t0 = time.time()
    while time.time() - t0 < 180:
        st = portal.invoke("swarm", {"op": "status"}).payload["status"]
        if st["running"] == 0 and st["done"] + st["error"] >= 2:
            break
        time.sleep(1)
    ok_all &= check("both agents completed", st["done"] == 2 and
                    st["error"] == 0)
    goals = portal.invoke("discover", {"op": "goals"}).payload["goals"]
    goal = next(g for g in goals if g["goal_id"] == "integration-demo")
    ok_all &= check("goal folder has 2 tasks", goal["task_count"] == 2)
    mon = portal.invoke("monitor", {"since": 0}).payload
    ok_all &= check(f"monitor streamed {len(mon['events'])} events",
                    len(mon["events"]) > 10)
    ok_all &= check("portal audit chains verify",
                    all(ex.audit_verify()
                        for ex in portal.executors.values()))
    ok_all &= check("social audit chains verify",
                    all(ex.audit_verify()
                        for ex in platform["social_node"].executors.values()))

    print("\n" + ("✅ ALL CHECKS PASSED" if ok_all else "❌ SOME CHECKS FAILED"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="IPP_Social integration demo")
    ap.add_argument("--live", action="store_true",
                    help="use the real DeepSeek provider")
    args = ap.parse_args()
    sys.exit(run(use_live=args.live))
