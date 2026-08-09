"""
agent_a2_create_a3_monitor.py — Drive agent_a2 to construct agent_a3
through its OWN tools. Purely observational — a2 does the work.

Run: python recursive_agents/agent_a2_create_a3_monitor.py
"""
from __future__ import annotations

import json, os, sys, time
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))


def log(step: str, detail: str, ok: bool = True) -> None:
    icon = "\u2705" if ok else "\u274c"  # ✅ or ❌
    print(f"  {icon} [{step}] {detail}")


def banner(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def main():
    os.chdir(str(WS))
    report: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": "agent_a2",
        "target": "agent_a3",
        "steps": {},
        "errors": [],
        "warnings": [],
    }

    banner("AGENT A2 -> CONSTRUCT AGENT A3 (MONITORED)")
    print("  Agent a2 uses its OWN tools. No bootstrap, no a1 involvement.")
    print(f"  Workspace: {WS}")

    # ── 0. Setup agent_a2 ─────────────────────────────────────────
    banner("0. SETUP — instantiate agent_a2 with its toolkit")

    from general_tools.graph import KnowledgeGraph
    from general_tools.encoder import EncoderLayer
    from LLMs.deepseek import MockProvider

    graph = KnowledgeGraph(auto_load=False)
    encoder = EncoderLayer()
    llm = MockProvider()

    from recursive_agents.agent_a2.agent_a2_tools.tool_registry import AgentA1Toolkit as AgentA2Toolkit
    toolkit = AgentA2Toolkit(agent_id="agent_a2", ws_root=str(WS),
                              graph=graph, encoder=encoder, llm=llm)
    toolkit.register_all()
    log("setup", f"Toolkit ready: {toolkit.count()} tools in {len(toolkit.categories)} categories", True)
    report["steps"]["setup"] = {"tool_count": toolkit.count(), "categories": list(toolkit.categories)}

    # Verify construction tools
    req = ["agent_plan", "agent_generate", "agent_create",
           "agent_evaluate", "agent_test", "agent_improve",
           "agent_deploy", "agent_status"]
    missing_req = [r for r in req if r not in toolkit.tools]
    if missing_req:
        log("setup", f"MISSING construction tools: {missing_req}", False)
        report["errors"].append(f"Missing construction tools: {missing_req}")
        return report
    log("setup", f"All {len(req)} construction tools present", True)

    from recursive_agents.agent_a2.agent_a2_tools.tool_base import ToolContext
    ctx = ToolContext(workspace_root=str(WS), agent=toolkit, agent_name="agent_a2")

    # ── 1. PLAN ───────────────────────────────────────────────────
    banner("1. agent_plan — THINK")
    try:
        result = toolkit.execute("agent_plan", {"agent_id": "a3"}, ctx)
        ok = result.ok
        plan = result.metadata
        log("plan", f"ok={ok}, target={plan.get('agent_id')}, level={plan.get('level')}", ok)
        log("plan", f"steps: {' -> '.join(plan.get('steps', []))}", ok)
        report["steps"]["plan"] = {"ok": ok, "metadata": plan}
        if not ok:
            report["errors"].append(f"plan failed: {result.error}")
    except Exception as e:
        log("plan", f"ERROR: {e}", False)
        report["errors"].append(f"plan exception: {e}")
        report["steps"]["plan"] = {"ok": False, "error": str(e)}

    # ── 2. GENERATE ───────────────────────────────────────────────
    banner("2. agent_generate — write a3 files to disk")
    try:
        result = toolkit.execute("agent_generate", {"agent_id": "a3", "level": 3}, ctx)
        ok = result.ok
        meta = result.metadata
        log("generate", f"ok={ok}, files_written={meta.get('files_written')}", ok)
        for f in (meta.get("files") or [])[:15]:
            log("generate", f"  wrote: {f}", True)
        report["steps"]["generate"] = {"ok": ok, "files_written": meta.get("files_written"), "files": meta.get("files")}
    except Exception as e:
        log("generate", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"generate exception: {e}")
        report["steps"]["generate"] = {"ok": False, "error": str(e)}

    # ── 3. CREATE ─────────────────────────────────────────────────
    banner("3. agent_create — Gamma-construct + verify 17 invariants")
    try:
        result = toolkit.execute("agent_create", {"agent_id": "a3", "level": 3}, ctx)
        ok = result.ok
        meta = result.metadata
        log("create", f"ok={ok}, engine_node={meta.get('engine_node')}, verified={meta.get('verified')}", ok)
        if not ok:
            report["errors"].append(f"create failed: {result.error}")
        report["steps"]["create"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("create", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"create exception: {e}")

    # ── 4. EVALUATE ───────────────────────────────────────────────
    banner("4. agent_evaluate — invariants + audit + channels")
    try:
        result = toolkit.execute("agent_evaluate", {"agent_id": "a3"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("evaluate", f"ok={ok}, channels: engine={meta.get('engine_channels')}, tools={meta.get('tools_channels')}", ok)
        log("evaluate", f"audit_chains={meta.get('audit_chains')}", meta.get('audit_chains', False))
        report["steps"]["evaluate"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("evaluate", f"ERROR: {e}", False)
        report["errors"].append(f"evaluate exception: {e}")

    # ── 5. TEST ───────────────────────────────────────────────────
    banner("5. agent_test — pipeline + latency -> feedback")
    try:
        result = toolkit.execute("agent_test", {"agent_id": "a3"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("test", f"ok={ok}, issues={meta.get('issues', [])}", ok)
        for check_name, check_val in meta.get("checks", {}).items():
            log("test", f"  {check_name}: {check_val}", check_val)
        report["steps"]["test"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("test", f"ERROR: {e}", False)
        report["errors"].append(f"test exception: {e}")

    # ── 6. IMPROVE ────────────────────────────────────────────────
    banner("6. agent_improve — test -> patch -> retest")
    try:
        result = toolkit.execute("agent_improve", {"agent_id": "a3", "iterations": 3}, ctx)
        ok = result.ok
        meta = result.metadata
        log("improve", f"ok={ok}, iterations={meta.get('iterations')}, patches={len(meta.get('patches', []))}", ok)
        for p in meta.get("patches", []):
            log("improve", f"  patch: {p}", True)
        for rnd in meta.get("rounds", []):
            log("improve", f"  round {rnd.get('round')}: ok={rnd.get('ok')}", rnd.get('ok', False))
        report["steps"]["improve"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("improve", f"ERROR: {e}", False)
        report["errors"].append(f"improve exception: {e}")

    # ── 7. DEPLOY ─────────────────────────────────────────────────
    banner("7. agent_deploy — register in the chain")
    try:
        result = toolkit.execute("agent_deploy", {"agent_id": "a3", "level": 3}, ctx)
        ok = result.ok
        meta = result.metadata
        log("deploy", f"ok={ok}, chain={meta.get('chain')}", ok)
        report["steps"]["deploy"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("deploy", f"ERROR: {e}", False)
        report["errors"].append(f"deploy exception: {e}")

    # ── 8. STATUS ─────────────────────────────────────────────────
    banner("8. agent_status — report the chain")
    try:
        result = toolkit.execute("agent_status", {}, ctx)
        ok = result.ok
        meta = result.metadata
        log("status", f"chain={meta.get('chain')}, constructed={meta.get('constructed')}", ok)
        report["steps"]["status"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("status", f"ERROR: {e}", False)

    # ── 9. VERIFY: Tool Count ─────────────────────────────────────
    banner("9. check_tool_count (must be >= 50)")
    try:
        result = toolkit.execute("check_tool_count", {"agent_id": "a3", "min_required": 50}, ctx)
        ok = result.ok
        meta = result.metadata
        log("check_tool_count", f"count={meta.get('tool_count')}, meets={meta.get('meets_threshold')}", meta.get('meets_threshold', False))
        report["steps"]["check_tool_count"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
        if not meta.get('meets_threshold'):
            report["errors"].append(f"TOOL COUNT < 50: {meta.get('tool_count')}")
    except Exception as e:
        log("check_tool_count", f"ERROR: {e}", False)

    # ── 10. VERIFY: Recursive Capability ──────────────────────────
    banner("10. check_recursive_capability (all 8 tools)")
    try:
        result = toolkit.execute("check_recursive_capability", {"agent_id": "a3"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("recursive_capability", f"has_all={meta.get('has_all')}, missing={meta.get('missing')}", meta.get('has_all', False))
        report["steps"]["check_recursive_capability"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("recursive_capability", f"ERROR: {e}", False)

    # ── 11. VERIFY: Engine Comprehensiveness ──────────────────────
    banner("11. evaluate_engine_comprehensiveness")
    try:
        result = toolkit.execute("evaluate_engine_comprehensiveness", {"agent_id": "a3"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("engine_comprehensiveness", f"found={meta.get('found')}, missing={meta.get('missing')}", meta.get('is_comprehensive', False))
        report["steps"]["evaluate_engine_comprehensiveness"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("engine_comprehensiveness", f"ERROR: {e}", False)

    # ── 12. ON-DISK CHECK ─────────────────────────────────────────
    banner("12. ON-DISK VERIFICATION")
    agent_a3_dir = WS / "recursive_agents" / "agent_a3"
    for sub in ["agent_a3_engine", "agent_a3_tools"]:
        subdir = agent_a3_dir / sub
        exists = subdir.exists()
        py_count = len(list(subdir.glob("*.py"))) if exists else 0
        ipp_json = (subdir / "IPP.json").exists()
        log("disk", f"{sub}: exists={exists}, py_files={py_count}, IPP.json={ipp_json}", exists and ipp_json)
        if not exists:
            report["errors"].append(f"Missing directory: {sub}")
        report["steps"].setdefault("disk_check", {})[sub] = {"exists": exists, "py_count": py_count, "ipp_json": ipp_json}

    for fname in ["README.md", "system_prompt.md"]:
        fp = agent_a3_dir / fname
        log("disk", f"{fname}: {fp.exists()}", fp.exists())

    # ── SUMMARY ───────────────────────────────────────────────────
    banner("SUMMARY")
    total_ok = sum(1 for s in report["steps"].values() if isinstance(s, dict) and s.get("ok") is True)
    total_steps = sum(1 for s in report["steps"].values() if isinstance(s, dict) and "ok" in s)
    error_count = len(report["errors"])

    print(f"  Steps passed: {total_ok}/{total_steps}")
    print(f"  Errors: {error_count}")
    print(f"  Chain: {toolkit.chain}")
    print(f"  Constructed: {sorted(toolkit.constructed)}")

    if report["errors"]:
        print(f"\n  !! ERRORS ({error_count}):")
        for e in report["errors"]:
            print(f"    X {e}")

    # Write reports
    rp = WS / "recursive_agents" / "monitor_report_agent_a2_a3.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    hr = WS / "recursive_agents" / "monitor_report_agent_a2_a3.md"
    lines = [
        f"# Agent A2 -> Agent A3 Construction Report",
        f"",
        f"**Timestamp**: {report['timestamp']}",
        f"**Agent**: {report['agent']} -> **Target**: {report['target']}",
        f"",
        f"## Step Results",
        f"",
        f"| Step | Result | Details |",
        f"|:---|:---|:---|",
    ]
    for step_name, step_data in report["steps"].items():
        s_ok = step_data.get("ok", "?") if isinstance(step_data, dict) else "?"
        icon = "OK" if s_ok is True else "FAIL" if s_ok is False else "?"
        detail = ""
        if isinstance(step_data, dict):
            if "tool_count" in step_data:
                detail = f"count={step_data['tool_count']}, meets={step_data.get('meets_threshold')}"
            elif "has_all" in step_data:
                detail = f"has_all={step_data.get('has_all')}, missing={step_data.get('missing')}"
            elif "files_written" in step_data:
                detail = f"{step_data['files_written']} files"
            elif "chain" in step_data:
                detail = f"chain={step_data['chain']}"
        lines.append(f"| {step_name} | {icon} | {detail} |")

    if report["errors"]:
        lines.append("")
        lines.append("## Errors")
        for e in report["errors"]:
            lines.append(f"- X {e}")

    lines.append("")
    lines.append(f"**Final chain**: {' -> '.join(toolkit.chain)}")
    lines.append(f"**Constructed**: {sorted(toolkit.constructed)}")
    hr.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  Full report: {rp}")
    print(f"  Human-readable: {hr}")

    return report


if __name__ == "__main__":
    main()
