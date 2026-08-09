"""
agent_a2_instruct_a3.py — Send ONE instruction to agent_a2, then monitor.
agent_a2 does ALL the work through its LLM loop + its own tools.
"""
from __future__ import annotations

import argparse, json, os, sys, time
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))


def main():
    ap = argparse.ArgumentParser(description="Instruct agent_a2 to create agent_a3")
    ap.add_argument("--live", action="store_true",
                    help="Use real DeepSeek LLM")
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()

    os.chdir(str(WS))

    print(f"\n{'='*70}")
    print(f"  INSTRUCT AGENT_A2 -> CREATE AGENT_A3 (LLM-DRIVEN)" if args.live
          else "  INSTRUCT AGENT_A2 -> CREATE AGENT_A3 (OFFLINE)")
    print(f"{'='*70}")

    from general_tools.graph import KnowledgeGraph
    from general_tools.encoder import EncoderLayer

    graph = KnowledgeGraph(auto_load=False)
    encoder = EncoderLayer()

    if args.live:
        from LLMs.deepseek import DeepSeekProvider
        llm = DeepSeekProvider(model=args.model)
        print("  Using DeepSeek live LLM")
    else:
        from LLMs.deepseek import MockProvider
        llm = MockProvider()
        print("  OFFLINE mode")

    from recursive_agents.agent_a2.agent_a2_tools.tool_registry import AgentA1Toolkit as AgentA2Toolkit
    toolkit = AgentA2Toolkit(agent_id="agent_a2", ws_root=str(WS),
                              graph=graph, encoder=encoder, llm=llm)
    toolkit.register_all()

    from recursive_agents.runtime.engine import RecursiveAgentEngine
    engine = RecursiveAgentEngine(
        graph=graph, encoder=encoder, llm=llm,
        agent_id="agent_a2", level=2, toolkit=toolkit,
    )

    print(f"  Engine: {engine.agent_id} (level {engine.level})")
    print(f"  Toolkit: {toolkit.count()} tools")
    print(f"  System prompt: {len(engine.system_prompt)} chars")

    instruction = (
        "Create the next recursive agent, agent_a3. Follow your operating "
        "procedure: agent_plan -> agent_generate -> agent_create -> "
        "agent_evaluate -> agent_test -> agent_improve -> agent_deploy -> "
        "agent_status -> verify tool count/recursive capability/engine "
        "comprehensiveness. Report what you did concisely."
    )

    print(f"\n  Instruction: {instruction[:120]}...")
    t0 = time.time()

    for event in engine.chat_stream(instruction):
        if event.tool:
            print(f"  [tool] {event.tool}")
        elif event.type in ("text", "message"):
            txt = (event.content or "")[:200]
            if txt.strip():
                print(f"  [text] {txt}")
        elif event.type == "done":
            print(f"  [done] rounds={event.rounds}")

    elapsed = time.time() - t0

    print(f"\n  Duration: {elapsed:.1f}s")
    print(f"  Chain: {toolkit.chain}")
    print(f"  Constructed: {sorted(toolkit.constructed)}")

    from pathlib import Path
    a3 = Path("recursive_agents/agent_a3")
    print(f"  agent_a3 on disk: {a3.exists()}")
    if a3.exists():
        py_count = sum(1 for _ in a3.rglob("*.py") if "__pycache__" not in str(_))
        print(f"  .py files in a3: {py_count}")


if __name__ == "__main__":
    main()
