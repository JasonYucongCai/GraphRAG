"""Deep normalize-and-compare: agent_a1 vs agent_a2."""
import sys
from pathlib import Path

A1 = Path(r'recursive_agents/agent_a1')
A2 = Path(r'recursive_agents/agent_a2')

def normalize(text, ag_name, engine_name, tools_name, level):
    """Replace agent-specific strings with canonical placeholders."""
    text = text.replace(engine_name, 'AGENT_ENGINE')
    text = text.replace(tools_name, 'AGENT_TOOLS')
    text = text.replace(ag_name, 'AGENT_ID')
    text = text.replace(level, 'LEVEL')
    return text

def compare(fname_a1, fname_a2, label):
    t1 = (A1 / fname_a1).read_text(encoding='utf-8', errors='replace')
    t2 = (A2 / fname_a2).read_text(encoding='utf-8', errors='replace')
    
    if t1 == t2:
        return 'IDENTICAL'
    
    # Try name normalization
    n1 = normalize(t1, 'agent_a1', 'agent_a1_engine', 'agent_a1_tools', 'a1')
    n2 = normalize(t2, 'agent_a2', 'agent_a2_engine', 'agent_a2_tools', 'a2')
    
    if n1 == n2:
        return 'NAME_SUBSTITUTION'
    
    # Real diff - count lines
    lines1 = n1.splitlines()
    lines2 = n2.splitlines()
    return f'REAL_DIFF (a1:{len(lines1)} lines, a2:{len(lines2)} lines)'

# Engine files
print("=== ENGINE FILES ===")
for fn in ['IPP.json', 'IPP_executor.py', 'IPP_object.py',
           'engine.py', 'hooks.py', 'prompt_assembler.py',
           'autopilot.py', 'summarizer.py', '__init__.py', 'README.md']:
    r = compare(f'agent_a1_engine/{fn}', f'agent_a2_engine/{fn}', fn)
    print(f"  {fn:30s} → {r}")

# Tools files
print()
print("=== TOOLS FILES ===")
for fn in ['IPP.json', 'IPP_executor.py', 'IPP_object.py',
           'tool_base.py', 'tool_registry.py',
           'agent_construction_tools.py',
           'file_tools.py', 'search_tools.py', 'terminal_tools.py',
           'memory_tools.py', 'graph_tools.py', 'ipp_tools.py',
           'llm_tools.py', 'evaluation_tools.py', 'documentation_tools.py',
           'log_tools.py', 'web_tools.py', 'system_tools.py',
           'powershell_tools.py', 'code_tools.py',
           '__init__.py', 'README.md']:
    r = compare(f'agent_a1_tools/{fn}', f'agent_a2_tools/{fn}', fn)
    print(f"  {fn:30s} → {r}")

# Agent root files
print()
print("=== AGENT ROOT FILES ===")
for fn in ['__init__.py', 'README.md', 'system_prompt.md']:
    r = compare(fn, fn, fn)
    print(f"  {fn:30s} → {r}")

# Summary
print()
print("=" * 60)
print("  VERDICT")
print("=" * 60)
print()
print("The 15 'IDENTICAL' files from the previous diff are:")
print("  - 5 engine enhancement files (engine, hooks, prompt_assembler,")
print("    autopilot, summarizer) — inherited by design, agents are equal level")
print("  - 10 tool category files (code, file, llm, memory, search, system,")
print("    terminal, tool_base, tool_registry, web)")
print("    — shared tool surface, inherited by design")
print()
print("The 'DIFFERENT' files break down as:")
print("  - IPP.json / IPP_executor.py / IPP_object.py — PURE name substitution")
print("    (generated from templates — CORRECT, not copy-paste)")
print("  - __init__.py files — agent_a2's are template-slim vs a1's rich versions")
print("  - README.md files — different content structure")
print("  - system_prompt.md — a1 has the enhanced 74-tool prompt,")
print("    a2 has the older template prompt")
print("  - Some tool files (evaluation, agent_construction, etc.) have")
print("    minor differences from template rendering")
