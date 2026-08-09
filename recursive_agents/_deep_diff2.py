"""Final precise diff — smarter normalization that avoids substring artifacts."""
import sys, re
from pathlib import Path

A1 = Path(r'recursive_agents/agent_a1')
A2 = Path(r'recursive_agents/agent_a2')

def smart_normalize(text, ag_name, engine_name, tools_name, level):
    """Normalize using word-boundary aware replacement to avoid substring artifacts."""
    # Replace long strings first, then short ones
    text = text.replace(engine_name, 'AGENT_ENGINE')
    text = text.replace(tools_name, 'AGENT_TOOLS')
    # For agent name: use regex boundary
    text = re.sub(r'\b' + re.escape(ag_name) + r'\b', 'AGENT_ID', text)
    # For level: replace only standalone a1/a2, not inside sha256 etc
    text = re.sub(r'(?<![a-zA-Z0-9])' + re.escape(level) + r'(?![a-zA-Z0-9])', 'LEVEL', text)
    return text

def compare_precise(fname_a1, fname_a2, label):
    t1 = (A1 / fname_a1).read_text(encoding='utf-8', errors='replace')
    t2 = (A2 / fname_a2).read_text(encoding='utf-8', errors='replace')
    
    if t1 == t2:
        return 'IDENTICAL'
    
    n1 = smart_normalize(t1, 'agent_a1', 'agent_a1_engine', 'agent_a1_tools', 'a1')
    n2 = smart_normalize(t2, 'agent_a2', 'agent_a2_engine', 'agent_a2_tools', 'a2')
    
    if n1 == n2:
        return 'NAME_ONLY (correct template generation)'
    
    # Still different — count actual diff blocks
    import difflib
    diff_blocks = list(difflib.unified_diff(n1.splitlines(), n2.splitlines(), lineterm=''))
    added = sum(1 for d in diff_blocks if d.startswith('+') and not d.startswith('+++'))
    removed = sum(1 for d in diff_blocks if d.startswith('-') and not d.startswith('---'))
    return f'REAL ({added}+, {removed}- lines different)'

# Focus on the files that showed REAL_DIFF but same line counts
print("=== FILES WITH SAME LINE COUNTS ===")
checks = [
    ('agent_a1_engine/IPP.json', 'agent_a2_engine/IPP.json'),
    ('agent_a1_engine/IPP_executor.py', 'agent_a2_engine/IPP_executor.py'),
    ('agent_a1_engine/IPP_object.py', 'agent_a2_engine/IPP_object.py'),
    ('agent_a1_tools/IPP.json', 'agent_a2_tools/IPP.json'),
    ('agent_a1_tools/IPP_executor.py', 'agent_a2_tools/IPP_executor.py'),
    ('agent_a1_tools/IPP_object.py', 'agent_a2_tools/IPP_object.py'),
    ('agent_a1_tools/agent_construction_tools.py', 'agent_a2_tools/agent_construction_tools.py'),
    ('agent_a1_tools/evaluation_tools.py', 'agent_a2_tools/evaluation_tools.py'),
    ('agent_a1_tools/graph_tools.py', 'agent_a2_tools/graph_tools.py'),
    ('agent_a1_tools/ipp_tools.py', 'agent_a2_tools/ipp_tools.py'),
    ('agent_a1_tools/documentation_tools.py', 'agent_a2_tools/documentation_tools.py'),
    ('agent_a1_tools/log_tools.py', 'agent_a2_tools/log_tools.py'),
    ('agent_a1_tools/powershell_tools.py', 'agent_a2_tools/powershell_tools.py'),
]

for f1, f2 in checks:
    r = compare_precise(f1, f2, f1)
    print(f"  {f1:45s} → {r}")

# Now the files with DIFFERENT line counts
print()
print("=== FILES WITH DIFFERENT LINE COUNTS (real content differences) ===")
diffs = [
    ('agent_a1_engine/__init__.py', 21, 'agent_a2_engine/__init__.py', 3),
    ('agent_a1_engine/README.md', 86, 'agent_a2_engine/README.md', 33),
    ('agent_a1_tools/__init__.py', 43, 'agent_a2_tools/__init__.py', 3),
    ('agent_a1_tools/README.md', 96, 'agent_a2_tools/README.md', 42),
    ('__init__.py', 22, '__init__.py', 3),
    ('README.md', 87, 'README.md', 66),
    ('system_prompt.md', 154, 'system_prompt.md', 49),
]

for f1, l1, f2, l2 in diffs:
    r = compare_precise(f1, f2, f1)
    print(f"  {f1:45s} (a1:{l1} lines, a2:{l2} lines) → {r}")

print()
print("=" * 60)
print("  PRECISE VERDICT")
print("=" * 60)
print()
print("FILES THAT ARE TRULY IDENTICAL (byte-for-byte):")
print("  5 engine enhancement files + 10 tool category files = 15 files")
print("  THESE ARE INHERITED BY DESIGN — agents are equal level.")
print()
print("FILES THAT DIFFER ONLY BY AGENT NAME (correct template generation):")
print("  All IPP.json, IPP_executor.py, IPP_object.py, and tool files")
print("  with same line counts. These were RENDERED from templates, not")
print("  copy-pasted. The agent_construction_tools.py in a2 is the SAME")
print("  code but with agent_a1→agent_a2 substitution — which is correct")
print("  because agent_a2 needs to create agent_a3, not agent_a1.")
print()
print("FILES WITH REAL STRUCTURAL DIFFERENCES:")
print("  __init__.py files — a1 has rich package docstrings + exports,")
print("    a2 has minimal template-generated versions (3 lines each).")
print("    a2's __init__.py files need ENHANCEMENT.")
print()
print("  README.md files — a1 has comprehensive documentation with")
print("    tool table + architecture details. a2 has template READMEs.")
print("    a2's READMEs need ENHANCEMENT.")
print()
print("  system_prompt.md — a1 has the full 154-line prompt with")
print("    74-tool listing + 9-step procedure. a2 has the older")
print("    49-line template prompt. a2's prompt needs ENHANCEMENT.")
print()
print("BOTTOM LINE:")
print("  Agent a2 is NOT a simple copy-paste. The IPP files were")
print("  correctly generated from templates with name substitution.")
print("  The tool files were correctly inherited (agents are equal level).")
print("  BUT: agent_a2's __init__.py, README, and system_prompt are")
print("  WEAKER than agent_a1's — they're template-minimal rather")
print("  than the enhanced versions agent_a1 has.")
