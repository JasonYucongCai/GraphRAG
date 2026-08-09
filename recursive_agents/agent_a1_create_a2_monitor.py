"""
agent_a1_create_a2_monitor.py — Drive agent_a1 to construct agent_a2
through its OWN tools and record everything.

Run: python recursive_agents/agent_a1_create_a2_monitor.py

This script does NOT copy/paste files. agent_a1's tools do the work:
  agent_plan → agent_generate → agent_create → agent_evaluate
  → agent_test → agent_improve → agent_deploy → agent_status
  → check_tool_count → check_recursive_capability
  → evaluate_engine_comprehensiveness
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))


def log(step: str, detail: str, ok: bool = True) -> None:
    icon = "✅" if ok else "❌"
    print(f"  {icon} [{step}] {detail}")


def banner(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def main():
    os.chdir(str(WS))
    report: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": "agent_a1",
        "target": "agent_a2",
        "steps": {},
        "errors": [],
        "warnings": [],
    }

    banner("AGENT A1 → CONSTRUCT AGENT A2 (MONITORED)")
    print("  Agent a1 uses its OWN tools. No bootstrap script.")
    print(f"  Workspace: {WS}")

    # ── 0. Setup ──────────────────────────────────────────────────
    banner("0. SETUP — instantiate agent_a1 with its toolkit")

    from general_tools.graph import KnowledgeGraph
    from general_tools.encoder import EncoderLayer
    from LLMs.deepseek import MockProvider

    graph = KnowledgeGraph(auto_load=False)
    encoder = EncoderLayer()
    llm = MockProvider()  # offline — tools work deterministically

    from recursive_agents.agent_a1.agent_a1_tools.tool_registry import AgentA1Toolkit
    toolkit = AgentA1Toolkit(agent_id="agent_a1", ws_root=str(WS),
                              graph=graph, encoder=encoder, llm=llm)
    toolkit.register_all()
    log("setup", f"Toolkit ready: {toolkit.count()} tools in {len(toolkit.categories)} categories", True)
    report["steps"]["setup"] = {"tool_count": toolkit.count(), "categories": list(toolkit.categories)}

    # ── Verify the 8 construction tools exist ─────────────────────
    req = ["agent_plan", "agent_generate", "agent_create",
           "agent_evaluate", "agent_test", "agent_improve",
           "agent_deploy", "agent_status"]
    missing_req = [r for r in req if r not in toolkit.tools]
    if missing_req:
        log("setup", f"MISSING construction tools: {missing_req}", False)
        report["errors"].append(f"Missing construction tools: {missing_req}")
        return report
    log("setup", f"All {len(req)} construction tools present", True)

    # Build a tool context
    from recursive_agents.agent_a1.agent_a1_tools.tool_base import ToolContext
    ctx = ToolContext(workspace_root=str(WS), agent=toolkit, agent_name="agent_a1")

    # ── 1. PLAN ───────────────────────────────────────────────────
    banner("1. agent_plan — THINK: deterministic construction plan")
    try:
        result = toolkit.execute("agent_plan", {"agent_id": "a2"}, ctx)
        ok = result.ok
        plan = result.metadata
        log("plan", f"ok={ok}, target={plan.get('agent_id')}, level={plan.get('level')}", ok)
        log("plan", f"steps: {' → '.join(plan.get('steps', []))}", ok)
        log("plan", f"verification: {plan.get('verification_required', [])}", ok)
        report["steps"]["plan"] = {"ok": ok, "metadata": plan}
        if not ok:
            report["errors"].append(f"plan failed: {result.error}")
    except Exception as e:
        log("plan", f"ERROR: {e}", False)
        report["errors"].append(f"plan exception: {e}")
        report["steps"]["plan"] = {"ok": False, "error": str(e)}

    # ── 2. GENERATE ───────────────────────────────────────────────
    banner("2. agent_generate — GENERATE: write files to disk")
    try:
        result = toolkit.execute("agent_generate", {"agent_id": "a2", "level": 2}, ctx)
        ok = result.ok
        meta = result.metadata
        log("generate", f"ok={ok}, files_written={meta.get('files_written')}", ok)
        files = meta.get("files", [])
        for f in files[:15]:
            log("generate", f"  wrote: {f}", True)
        if not ok:
            report["errors"].append(f"generate failed: {result.error}")
        report["steps"]["generate"] = {"ok": ok, "files_written": meta.get("files_written"), "files": meta.get("files")}
    except Exception as e:
        log("generate", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"generate exception: {e}")
        report["steps"]["generate"] = {"ok": False, "error": str(e)}

    # ── 3. CREATE ─────────────────────────────────────────────────
    banner("3. agent_create — CREATE: Γ-construct + verify 17 invariants")
    try:
        result = toolkit.execute("agent_create", {"agent_id": "a2", "level": 2}, ctx)
        ok = result.ok
        meta = result.metadata
        log("create", f"ok={ok}, engine_node={meta.get('engine_node')}, tools_node={meta.get('tools_node')}", ok)
        log("create", f"verified={meta.get('verified')}, engine_failures={meta.get('engine_failures')}, tools_failures={meta.get('tools_failures')}", meta.get('verified', False))
        if not ok:
            report["errors"].append(f"create failed: {result.error}")
        report["steps"]["create"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("create", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"create exception: {e}")
        report["steps"]["create"] = {"ok": False, "error": str(e)}

    # ── 4. EVALUATE ───────────────────────────────────────────────
    banner("4. agent_evaluate — EVALUATE: invariants + audit + channels")
    try:
        result = toolkit.execute("agent_evaluate", {"agent_id": "a2"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("evaluate", f"ok={ok}, engine_channels={meta.get('engine_channels')}", ok)
        log("evaluate", f"tools_channels={meta.get('tools_channels')}", ok)
        log("evaluate", f"audit_chains={meta.get('audit_chains')}", meta.get('audit_chains', False))
        if not ok:
            report["errors"].append(f"evaluate failed: {result.error}")
        report["steps"]["evaluate"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("evaluate", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"evaluate exception: {e}")
        report["steps"]["evaluate"] = {"ok": False, "error": str(e)}

    # ── 5. TEST ───────────────────────────────────────────────────
    banner("5. agent_test — TEST: pipeline + latency probe → feedback")
    try:
        result = toolkit.execute("agent_test", {"agent_id": "a2"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("test", f"ok={ok}, issues={meta.get('issues', [])}", ok)
        checks = meta.get("checks", {})
        for check_name, check_val in checks.items():
            log("test", f"  {check_name}: {check_val}", check_val)
        report["steps"]["test"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("test", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"test exception: {e}")
        report["steps"]["test"] = {"ok": False, "error": str(e)}

    # ── 6. IMPROVE ────────────────────────────────────────────────
    banner("6. agent_improve — IMPROVE: test → patch → retest")
    try:
        result = toolkit.execute("agent_improve", {"agent_id": "a2", "iterations": 3}, ctx)
        ok = result.ok
        meta = result.metadata
        log("improve", f"ok={ok}, iterations={meta.get('iterations')}, patches={len(meta.get('patches', []))}", ok)
        patches = meta.get("patches", [])
        for p in patches:
            log("improve", f"  patch: {p}", True)
        rounds = meta.get("rounds", [])
        for r in rounds:
            log("improve", f"  round {r.get('round')}: ok={r.get('ok')}", r.get('ok', False))
        report["steps"]["improve"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("improve", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"improve exception: {e}")
        report["steps"]["improve"] = {"ok": False, "error": str(e)}

    # ── 7. DEPLOY ─────────────────────────────────────────────────
    banner("7. agent_deploy — DEPLOY: register in the chain")
    try:
        result = toolkit.execute("agent_deploy", {"agent_id": "a2", "level": 2}, ctx)
        ok = result.ok
        meta = result.metadata
        log("deploy", f"ok={ok}, chain={meta.get('chain')}", ok)
        report["steps"]["deploy"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("deploy", f"ERROR: {e}", False)
        import traceback; traceback.print_exc()
        report["errors"].append(f"deploy exception: {e}")
        report["steps"]["deploy"] = {"ok": False, "error": str(e)}

    # ── 8. STATUS ─────────────────────────────────────────────────
    banner("8. agent_status — STATUS: report the chain")
    try:
        result = toolkit.execute("agent_status", {}, ctx)
        ok = result.ok
        meta = result.metadata
        log("status", f"chain={meta.get('chain')}, constructed={meta.get('constructed')}", ok)
        report["steps"]["status"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
    except Exception as e:
        log("status", f"ERROR: {e}", False)
        report["steps"]["status"] = {"ok": False, "error": str(e)}

    # ── 9. VERIFY: Tool Count ─────────────────────────────────────
    banner("9. VERIFY — check_tool_count (must be >= 50)")
    try:
        result = toolkit.execute("check_tool_count", {"agent_id": "a2", "min_required": 50}, ctx)
        ok = result.ok
        meta = result.metadata
        log("check_tool_count", f"count={meta.get('tool_count')}, meets_threshold={meta.get('meets_threshold')}", meta.get('meets_threshold', False))
        report["steps"]["check_tool_count"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
        if not meta.get('meets_threshold'):
            report["errors"].append(f"TOOL COUNT FAILURE: {meta.get('tool_count')} < 50")
    except Exception as e:
        log("check_tool_count", f"ERROR: {e}", False)
        report["errors"].append(f"check_tool_count exception: {e}")

    # ── 10. VERIFY: Recursive Capability ──────────────────────────
    banner("10. VERIFY — check_recursive_capability (all 8 tools)")
    try:
        result = toolkit.execute("check_recursive_capability", {"agent_id": "a2"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("recursive_capability", f"has_all={meta.get('has_all')}, missing={meta.get('missing')}", meta.get('has_all', False))
        report["steps"]["check_recursive_capability"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
        if not meta.get('has_all'):
            report["errors"].append(f"RECURSIVE CAPABILITY FAILURE: missing {meta.get('missing')}")
    except Exception as e:
        log("recursive_capability", f"ERROR: {e}", False)
        report["errors"].append(f"check_recursive_capability exception: {e}")

    # ── 11. VERIFY: Engine Comprehensiveness ──────────────────────
    banner("11. VERIFY — evaluate_engine_comprehensiveness")
    try:
        result = toolkit.execute("evaluate_engine_comprehensiveness", {"agent_id": "a2"}, ctx)
        ok = result.ok
        meta = result.metadata
        log("engine_comprehensiveness", f"found={meta.get('found')}, missing={meta.get('missing')}", meta.get('is_comprehensive', False))
        report["steps"]["evaluate_engine_comprehensiveness"] = {"ok": ok, **{k: v for k, v in meta.items() if k != 'ok'}}
        if not meta.get('is_comprehensive'):
            report["errors"].append(f"ENGINE COMPREHENSIVENESS FAILURE: missing {meta.get('missing')}")
    except Exception as e:
        log("engine_comprehensiveness", f"ERROR: {e}", False)
        report["errors"].append(f"evaluate_engine_comprehensiveness exception: {e}")

    # ── 12. VERIFY: Check agent_a2 on disk ───────────────────────
    banner("12. ON-DISK VERIFICATION")
    agent_a2_dir = WS / "recursive_agents" / "agent_a2"
    for sub in ["agent_a2_engine", "agent_a2_tools"]:
        subdir = agent_a2_dir / sub
        exists = subdir.exists()
        py_count = len(list(subdir.glob("*.py"))) if exists else 0
        ipp_json = (subdir / "IPP.json").exists()
        log("disk", f"{sub}: exists={exists}, py_files={py_count}, IPP.json={ipp_json}", exists and ipp_json)
        if not exists:
            report["errors"].append(f"Missing directory: {sub}")
        report["steps"].setdefault("disk_check", {})[sub] = {"exists": exists, "py_count": py_count, "ipp_json": ipp_json}

    readme = agent_a2_dir / "README.md"
    prompt = agent_a2_dir / "system_prompt.md"
    log("disk", f"README.md: {readme.exists()}", readme.exists())
    log("disk", f"system_prompt.md: {prompt.exists()}", prompt.exists())
    if not readme.exists():
        report["errors"].append("Missing agent_a2/README.md")
    if not prompt.exists():
        report["errors"].append("Missing agent_a2/system_prompt.md")

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
        print(f"\n  ⚠️  ERRORS ({error_count}):")
        for e in report["errors"]:
            print(f"    ❌ {e}")

    # Write report
    report_path = WS / "recursive_agents" / "monitor_report_agent_a1_a2.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Full report written to: {report_path}")

    # Write human-readable report
    hr_path = WS / "recursive_agents" / "monitor_report_agent_a1_a2.md"
    lines = [
        f"# Agent A1 → Agent A2 Construction Report",
        f"",
        f"**Timestamp**: {report['timestamp']}",
        f"**Agent**: {report['agent']} → **Target**: {report['target']}",
        f"",
        f"## Step Results",
        f"",
        f"| Step | Result | Details |",
        f"|:---|:---|:---|",
    ]
    for step_name, step_data in report["steps"].items():
        s_ok = step_data.get("ok", "?") if isinstance(step_data, dict) else "?"
        icon = "✅" if s_ok is True else "❌" if s_ok is False else "⚠️"
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
            lines.append(f"- ❌ {e}")

    lines.append("")
    lines.append(f"**Final chain**: {' → '.join(toolkit.chain)}")
    lines.append(f"**Constructed**: {sorted(toolkit.constructed)}")
    hr_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Human-readable report: {hr_path}")

    return report


if __name__ == "__main__":
    main()
