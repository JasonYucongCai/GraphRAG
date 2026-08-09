"""
agent_a1_instruct_a2.py — Send ONE instruction to agent_a1, then monitor.

agent_a1 does ALL the work through its LLM loop + its own tools.
This script only: instantiates agent_a1, sends the message,
and logs the trace. Nothing more.

Run:  python recursive_agents/agent_a1_instruct_a2.py [--live]

Without --live: uses MockProvider, tools run but LLM doesn't think.
With --live:    uses real DeepSeek, the LLM drives the construction.
"""
from __future__ import annotations

import json, os, sys, time
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))


def banner(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Instruct agent_a1 to create agent_a2")
    ap.add_argument("--live", action="store_true",
                    help="Use real DeepSeek LLM (otherwise MockProvider)")
    ap.add_argument("--model", type=str, default=None,
                    help="Model override (default: config)")
    args = ap.parse_args()

    os.chdir(str(WS))

    banner("INSTRUCT AGENT_A1 → CREATE AGENT_A2 (LLM-DRIVEN)" if args.live
           else "INSTRUCT AGENT_A1 → CREATE AGENT_A2 (OFFLINE)")

    # ── 1. Setup ──────────────────────────────────────────────────
    print("  Setting up agent_a1 engine + toolkit...")

    from general_tools.graph import KnowledgeGraph
    from general_tools.encoder import EncoderLayer

    graph = KnowledgeGraph(auto_load=False)
    encoder = EncoderLayer()

    if args.live:
        print("  Connecting to DeepSeek...")
        from LLMs.deepseek import DeepSeekProvider
        llm = DeepSeekProvider(model=args.model)
    else:
        from LLMs.deepseek import MockProvider
        llm = MockProvider()
        print("  OFFLINE mode — LLM will not respond (MockProvider)")

    from recursive_agents.agent_a1.agent_a1_tools.tool_registry import AgentA1Toolkit
    toolkit = AgentA1Toolkit(agent_id="agent_a1", ws_root=str(WS),
                              graph=graph, encoder=encoder, llm=llm)
    toolkit.register_all()

    from recursive_agents.runtime.engine import RecursiveAgentEngine
    engine = RecursiveAgentEngine(
        graph=graph, encoder=encoder, llm=llm,
        agent_id="agent_a1", level=1, toolkit=toolkit,
    )

    print(f"  Engine: {engine.agent_id} (level {engine.level})")
    print(f"  Toolkit: {toolkit.count()} tools")
    print(f"  System prompt: {len(engine.system_prompt)} chars loaded")

    # ── 2. Send instruction ───────────────────────────────────────
    instruction = (
        "Create the next recursive agent, agent_a2. Follow your operating "
        "procedure: agent_plan → agent_generate → agent_create → "
        "agent_evaluate → agent_test → agent_improve → agent_deploy → "
        "agent_status. Verify tool count >= 50, recursive capability, "
        "engine comprehensiveness. Read generated files to review them. "
        "Report what you did concisely."
    )

    banner("SENDING INSTRUCTION")
    print(f"  To: {engine.agent_id}")
    print(f"  Task: {instruction[:120]}...")

    t0 = time.time()
    trace_entries: list[dict] = []
    answer = ""

    banner("AGENT TRACE (LLM LOOP)")
    for event in engine.chat_stream(instruction):
        entry = {
            "type": event.type,
            "timestamp": time.time() - t0,
        }
        if event.tool:
            entry["tool"] = event.tool
            print(f"  [tool_call]  {event.tool}")
            if event.args:
                args_str = json.dumps(event.args, ensure_ascii=False)
                print(f"               args: {args_str[:200]}")
        if event.content and event.type in ("text", "message", "message_delta"):
            content = event.content
            if event.type == "message_delta":
                pass  # streaming deltas are too noisy
            else:
                print(f"  [text]       {content[:300]}")
                answer += (content or "")
        if event.type == "tool_result":
            result_preview = str(event.content)[:200] if event.content else ""
            print(f"  [tool_result] {event.tool}: {result_preview}")
        if event.error:
            entry["error"] = event.error
            print(f"  [ERROR]      {event.error}")
        if event.type == "done":
            entry["rounds"] = event.rounds
            entry["usage"] = event.usage
        trace_entries.append(entry)

    elapsed = time.time() - t0

    # ── 3. Summary ────────────────────────────────────────────────
    banner("SUMMARY")
    tool_calls_made = [e for e in trace_entries if e["type"] == "tool_call"]
    tools_used = [e["tool"] for e in tool_calls_made]
    print(f"  Answer:   {answer[:300]}")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Tool calls: {len(tool_calls_made)}")
    print(f"  Tools used: {sorted(set(tools_used))}")
    print(f"  Chain: {toolkit.chain}")
    print(f"  Constructed: {sorted(toolkit.constructed)}")

    if "agent_a2" in toolkit.chain:
        print("\n  ✅ Agent a2 is in the chain — construction complete.")

        # Quick verify
        from recursive_agents.agent_a1.agent_a1_tools.tool_base import ToolContext
        ctx = type("Ctx", (), {"workspace_root": str(WS), "agent": toolkit})()
        for check in ["check_tool_count", "check_recursive_capability",
                      "evaluate_engine_comprehensiveness"]:
            try:
                result = toolkit.execute(check, {"agent_id": "a2"}, ctx)
                meta = result.metadata
                ok = meta.get("meets_threshold") or meta.get("has_all") or meta.get("is_comprehensive")
                print(f"  {check}: {'PASS' if ok else 'FAIL'} {meta}")
            except Exception as e:
                print(f"  {check}: ERROR {e}")
    else:
        print("\n  ❌ Agent a2 NOT in chain.")

    # Write trace
    trace_path = WS / "recursive_agents" / "llm_trace_agent_a1_a2.json"
    trace_path.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": "agent_a1",
        "target": "agent_a2",
        "live": args.live,
        "answer": answer[:2000],
        "elapsed": elapsed,
        "tool_calls": len(tool_calls_made),
        "tools_used": sorted(set(tools_used)),
        "chain": list(toolkit.chain),
        "constructed": sorted(toolkit.constructed),
        "trace": trace_entries[-50:],  # last 50 entries
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Full trace: {trace_path}")


if __name__ == "__main__":
    main()
