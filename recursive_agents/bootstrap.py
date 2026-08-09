"""
recursive_agents.bootstrap — Section A: build agent_a1 FOR REAL, then let
agent_a1's OWN tools create agent_a2, and agent_a2's tools create a3.

Run:  python -m recursive_agents.bootstrap [--live]

The chain (the Rust/C/C++ bootstrap analogy — NO copy-paste):

  0. agent_a1 is built HERE — a REAL agent: its engine (RecursiveAgentEngine)
     + its OWN toolkit (AgentToolkit: the REAL agent-construction tools —
     agent_generate literally writes the next agent's folders, agent_create
     constructs its IPP nodes through Γ, agent_test runs the pipeline,
     agent_improve patches, agent_deploy registers). Its IPP nodes are
     constructed through Γ from the engine F-file; ALL 17 invariants
     verified. ← THE FIRST COMPILATION
  1. agent_a1 is INSTRUCTED to create agent_a2 — the instruction is
     executed through agent_a1's OWN tools node (every step flows through
     the guardrail envelope, audited): agent_plan → agent_generate →
     agent_create → agent_evaluate → agent_test → agent_improve →
     agent_deploy. The files on disk are written BY agent_a1's tool.
  2. agent_a2 — which has the SAME toolkit — is instructed to create
     agent_a3 through ITS OWN tools node. The ability recurs.
  3. The chain is verified: every agent ALL 17 OK + audit chains + READMEs.

The AgentToolkit (recursive_agents.runtime.toolkit) is a sync port of the
Copilot agent architecture (assets/copilot_agent_tools): per-agent tool
registry with the four-phase lifecycle. With --live, the instructions
are also sent through each agent's chat channel (the LLM drives the
tools); offline, the same plan runs deterministically through the tools.
"""
from __future__ import annotations

import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
if str(WS) not in sys.path:
    sys.path.insert(0, str(WS))

INSTRUCTION_A1 = (
    "Create the next recursive agent, agent_a2, then evaluate it, test it "
    "with feedback and keep improving it until it passes; then deploy it "
    "into the chain.")
INSTRUCTION_A2 = (
    "Create the next recursive agent, agent_a3, then evaluate it and "
    "deploy it into the chain.")


def check(name: str, cond: bool) -> bool:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    return cond


def run(use_live: bool = False) -> int:
    ok_all = True
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Recursive agents — REAL self-adaptive chain                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    from general_tools.graph import KnowledgeGraph
    from general_tools.encoder import EncoderLayer
    from LLMs.deepseek import MockProvider
    from recursive_agents.runtime.toolkit import AgentToolkit
    from recursive_agents.runtime.engine import RecursiveAgentEngine
    from recursive_agents.runtime.templates import build as tpl_build
    from IPP.IPP_constructor import IPPConstructor
    from IPP.IPP_registry import GraphContext
    from IPP.IPP_verify import verify_node

    graph = KnowledgeGraph(auto_load=False)      # offline, hermetic
    encoder = EncoderLayer()
    llm = None if use_live else MockProvider()

    print("\n=== 0. FIRST COMPILATION — build agent_a1 FOR REAL ===")
    toolkit = AgentToolkit(agent_id="agent_a1", ws_root=str(WS),
                           graph=graph, encoder=encoder, llm=llm)
    engine_a1 = RecursiveAgentEngine(
        graph=graph, encoder=encoder, llm=llm,
        agent_id="agent_a1", level=1, toolkit=toolkit)

    # a1's folders from the template sources (its own engine + tools)
    engine_f, tools_f = tpl_build("agent_a1", "agent_a1_engine",
                                  "agent_a1_tools", level=1,
                                  generated_by="the recursive compiler",
                                  root=str(WS))
    # a1's IPP nodes constructed through Γ from those F-files
    ctx = GraphContext()
    ctx.bind("engine", engine_a1)
    ctx.bind("toolkit", toolkit)
    ctx.bind("agent_id", "agent_a1")
    from recursive_agents.runtime.engine import RECURSIVE_TOOL_NAMES
    ctx.bind("tool_names", list(RECURSIVE_TOOL_NAMES))

    engine_exec = __import__(
        "recursive_agents.agent_a1.agent_a1_engine.IPP_executor",
        fromlist=["AgentExecutor"])
    tools_exec = __import__(
        "recursive_agents.agent_a1.agent_a1_tools.IPP_executor",
        fromlist=["ToolExecutor"])
    gamma_e = IPPConstructor(
        ctx, executor_classes={ch: engine_exec.AgentExecutor
                               for ch in ("ground", "chat", "chat_stream")})
    engine_node = gamma_e.construct_file(engine_f, ctx)
    gamma_e.recall_scope(engine_node)
    ctx.register_node(engine_node)
    gamma_t = IPPConstructor(
        ctx, executor_classes={ch: tools_exec.ToolExecutor
                               for ch in toolkit.tools})
    tools_node = gamma_t.construct_file(tools_f, ctx)
    gamma_t.recall_scope(tools_node)
    ctx.register_node(tools_node)
    engine_a1.node = engine_node
    engine_a1._tools_node = tools_node
    engine_a1._ipp_context = ctx
    toolkit.constructed["agent_a1"] = engine_a1
    toolkit.chain.append("agent_a1")

    ok_all &= check("a1 engine channels",
                    set(engine_a1.node.channels) ==
                    {"ground", "chat", "chat_stream"})
    ok_all &= check("a1 tools channels = REAL construction suite",
                    {"agent_plan", "agent_generate", "agent_create",
                     "agent_evaluate", "agent_test", "agent_improve",
                     "agent_deploy", "agent_status"}
                    <= set(engine_a1._tools_node.channels))
    ok_all &= check("a1 ALL 17 invariants", not verify_node(engine_node)
                    and not verify_node(tools_node))
    ok_all &= check("a1 audit chains",
                    all(ex.audit_verify()
                        for ex in engine_a1.node.executors.values())
                    and all(ex.audit_verify()
                            for ex in tools_node.executors.values()))

    print("\n=== 1. INSTRUCT agent_a1 → create agent_a2 (a1's OWN TOOLS) ===")
    print(f"     instruction: {INSTRUCTION_A1[:80]}…")
    ok_all = _drive_with_tools(engine_a1, "a2", 2, ok_all)
    engine_a2 = toolkit.constructed["agent_a2"]

    print("\n=== 2. INSTRUCT agent_a2 → create agent_a3 (the ability recurs) ===")
    print(f"     instruction: {INSTRUCTION_A2[:80]}…")
    ok_all = _drive_with_tools(engine_a2, "a3", 3, ok_all)
    engine_a3 = toolkit.constructed["agent_a3"]

    print("\n=== 3. the chain — every agent verified + documented ===")
    for name, engine in (("agent_a1", engine_a1),
                         ("agent_a2", engine_a2),
                         ("agent_a3", engine_a3)):
        ok = (not verify_node(engine.node)
              and not verify_node(engine._tools_node))
        ok_all &= check(f"{name}: ALL 17 OK",
                        ok and all(ex.audit_verify()
                                   for ex in engine.node.executors.values())
                        and all(ex.audit_verify()
                                for ex in
                                engine._tools_node.executors.values()))
        for rel in ("README.md", "system_prompt.md",
                    f"{name}_engine/README.md", f"{name}_tools/README.md"):
            ok_all &= check(f"{name} {rel}",
                            (WS / "recursive_agents" / name / rel).exists())
        print(f"      {name}: {engine.node.node_id} + "
              f"{engine._tools_node.node_id} (level {engine.level})")
    st = engine_a1._tools_node.invoke("agent_status", {}).payload
    ok_all &= check(f"chain status via agent_status: "
                    f"{st.get('metadata', {}).get('chain')}",
                    bool(st.get("ok")) and
                    len(st.get("metadata", {}).get("chain", [])) == 3)

    if use_live:
        print("\n=== 4. LIVE: the instruction drives the chat loop ===")
        answer, trace = engine_a1.run_with_trace(INSTRUCTION_A1)
        calls = [t for t in trace if t.get("type") == "tool_call"]
        ok_all &= check(f"chat answered ({len(answer)} chars)", bool(answer))
        ok_all &= check(f"chat used the construction tools: "
                        f"{[c['tool'] for c in calls]}",
                        any(c["tool"] in ("agent_create", "agent_improve",
                                          "agent_test", "agent_plan")
                            for c in calls))

    print("\n" + ("✅ ALL RECURSIVE CHECKS PASSED" if ok_all
                  else "❌ SOME CHECKS FAILED"))
    return 0 if ok_all else 1


def _drive_with_tools(engine, agent_id: str, level: int, ok_all: bool) -> bool:
    """Execute the agent's construction PLAN through its OWN tools node —
    every step through the guardrail envelope, audited. The files on disk
    are written BY the agent's own agent_generate tool."""
    tools = engine._tools_node

    r = tools.invoke("agent_plan", {"agent_id": agent_id}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} THINK: agent_plan → "
                    f"{meta.get('agent_id')}",
                    bool(r.get("ok")))
    r = tools.invoke("agent_generate", {"agent_id": agent_id,
                                        "level": level}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} GENERATE: folders written "
                    f"(by {meta.get('generated_by')})",
                    bool(r.get("ok")) and
                    Path(meta.get("folders", {}).get("engine", "?")).exists())
    r = tools.invoke("agent_create", {"agent_id": agent_id,
                                      "level": level}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} CREATE: {meta.get('agent_id')} "
                    f"constructed + verified",
                    bool(r.get("ok")) and bool(meta.get("verified")))
    r = tools.invoke("agent_evaluate", {"agent_id": agent_id}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} EVALUATE: ALL 17 OK + audits",
                    bool(r.get("ok")) and bool(meta.get("audit_chains")))
    r = tools.invoke("agent_test", {"agent_id": agent_id}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} TEST: feedback collected",
                    "issues" in meta)
    r = tools.invoke("agent_improve", {"agent_id": agent_id,
                                       "iterations": 3}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} IMPROVE: {meta.get('iterations')} rounds"
                    + (f" + patch {meta.get('patches', [''])[0][:40]}"
                       if meta.get("patches") else ""),
                    bool(meta.get("iterations")) and bool(meta.get("patches")))
    ok_all &= check(f"{engine.agent_id} IMPROVE: target passes",
                    bool(meta.get("final", {}).get("ok")))
    r = tools.invoke("agent_deploy", {"agent_id": agent_id,
                                      "level": level}).payload
    meta = r.get("metadata", {})
    ok_all &= check(f"{engine.agent_id} DEPLOY: chain = {meta.get('chain')}",
                    bool(r.get("ok")) and
                    f"agent_{agent_id}" in (meta.get("chain") or []))
    return ok_all


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="recursive agents bootstrap")
    ap.add_argument("--live", action="store_true",
                    help="use the real DeepSeek provider (drives the chat)")
    args = ap.parse_args()
    sys.exit(run(use_live=args.live))
