"""Diff agent_a1 vs agent_a2 — find exactly what differs."""
import sys, os
sys.path.insert(0, '.')

A1 = r'recursive_agents\agent_a1'
A2 = r'recursive_agents\agent_a2'

# Map agent_a1 files to their agent_a2 equivalents
# Replace agent_a1 → agent_a2 in path
import difflib
from pathlib import Path

def read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except:
        return None

def compare(label1, path1, label2, path2):
    t1 = read(path1)
    t2 = read(path2)
    if t1 is None and t2 is None:
        return None, None, 'BOTH_MISSING'
    if t1 is None:
        return None, None, 'A1_MISSING'
    if t2 is None:
        return None, None, 'A2_MISSING'
    if t1 == t2:
        return t1, t2, 'IDENTICAL'
    # Count diff lines
    diff = list(difflib.unified_diff(
        t1.splitlines(keepends=True),
        t2.splitlines(keepends=True),
        fromfile=label1, tofile=label2))
    added = sum(1 for d in diff if d.startswith('+') and not d.startswith('+++'))
    removed = sum(1 for d in diff if d.startswith('-') and not d.startswith('---'))
    return t1, t2, 'DIFFERENT', added, removed, len(diff)

# Build file map
import glob

a1_files = {}
for root, dirs, files in os.walk(A1):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        full = os.path.join(root, f)
        rel = os.path.relpath(full, A1)
        a1_files[rel] = full

a2_files = {}
for root, dirs, files in os.walk(A2):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        full = os.path.join(root, f)
        rel = os.path.relpath(full, A2)
        a2_files[rel] = full

# Transform agent_a1 paths to expected agent_a2 paths
def a1_to_a2(rel):
    return rel.replace('agent_a1_engine', 'agent_a2_engine').replace(
        'agent_a1_tools', 'agent_a2_tools').replace('agent_a1', 'agent_a2')

all_files = set(a1_files.keys()) | set(a2_files.keys())
identical = []
different = []
only_a1 = []
only_a2 = []

for rel1 in sorted(a1_files):
    rel2 = a1_to_a2(rel1)
    if rel2 in a2_files:
        result = compare(rel1, a1_files[rel1], rel2, a2_files[rel2])
        status = result[2]
        if status == 'IDENTICAL':
            identical.append(rel1)
        elif status == 'DIFFERENT':
            different.append((rel1, result[3], result[4], result[5]))
    else:
        only_a1.append(rel1)

for rel2 in sorted(a2_files):
    # Check if any a1 file maps to this
    found = False
    for rel1 in a1_files:
        if a1_to_a2(rel1) == rel2:
            found = True
            break
    if not found:
        only_a2.append(rel2)

print("=" * 70)
print("  AGENT A1 vs AGENT A2 — FILE-BY-FILE COMPARISON")
print("=" * 70)
print()

print(f"IDENTICAL files: {len(identical)}")
for f in identical:
    print(f"  =  {f}")

print()
print(f"DIFFERENT files: {len(different)}")
for rel, added, removed, total in different:
    print(f"  ≠  {rel}  (+{added} -{removed} = {total} diff lines)")

print()
print(f"ONLY in agent_a1 (no a2 counterpart): {len(only_a1)}")
for f in only_a1:
    print(f"  a1> {f}")

print()
print(f"ONLY in agent_a2 (no a1 counterpart): {len(only_a2)}")
for f in only_a2:
    print(f"  a2> {f}")

# Show specific diff details for the generated-only files
print()
print("=" * 70)
print("  DETAIL: IPP.json differences (the 'generated' difference)")
print("=" * 70)
for fname in ['agent_a1_engine/IPP.json', 'agent_a1_tools/IPP.json']:
    t1 = read(os.path.join(A1, fname))
    t2 = read(os.path.join(A2, a1_to_a2(fname)))
    if t1 and t2:
        # Just show the specific string replacements
        import re
        # Find all agent_a1 → agent_a2 replacements
        count_a1_in_a1 = t1.count('agent_a1')
        count_a2_in_a2 = t2.count('agent_a2')
        print(f"\n{fname}:")
        print(f"  'agent_a1' occurrences in a1: {count_a1_in_a1}")
        print(f"  'agent_a2' occurrences in a2: {count_a2_in_a2}")
        # Verify the only diff is the agent name
        t1_norm = t1.replace('agent_a1', 'AGENT_X').replace('a1', 'X')
        t2_norm = t2.replace('agent_a2', 'AGENT_X').replace('a2', 'X')
        if t1_norm == t2_norm:
            print(f"  → Diff is PURELY agent name substitution (agent_a1↔agent_a2, a1↔a2)")
            print(f"  → This is a TRUE generated agent, not a copy-paste")
        else:
            print(f"  → Additional differences beyond name substitution")

# Show specific diff for __init__.py
print()
print("=" * 70)
print("  DETAIL: __init__.py comparison")
print("=" * 70)
for fname in ['__init__.py', 'agent_a1_engine/__init__.py', 'agent_a1_tools/__init__.py']:
    t1 = read(os.path.join(A1, fname))
    t2 = read(os.path.join(A2, a1_to_a2(fname)))
    if t1 and t2:
        equal = (t1.replace('agent_a1', 'AGENT_X').replace('a1','X') == 
                 t2.replace('agent_a2', 'AGENT_X').replace('a2','X'))
        print(f"  {fname}: {'IDENTICAL (pure name substitution)' if equal else 'REAL DIFFERENCES'}")

print()
print("=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"  Total a1 files: {len(a1_files)}")
print(f"  Total a2 files: {len(a2_files)}")
print(f"  Identical:       {len(identical)}")
print(f"  Different:       {len(different)}")
print(f"  Only in a1:      {len(only_a1)}")
print(f"  Only in a2:      {len(only_a2)}")
