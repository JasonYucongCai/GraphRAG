"""Three-way diff: agent_a1 vs agent_a2 vs agent_a3 — smart normalization."""
import sys, re, json
from pathlib import Path

A1 = Path("recursive_agents/agent_a1")
A2 = Path("recursive_agents/agent_a2")
A3 = Path("recursive_agents/agent_a3")

def read(p):
    try: return p.read_text(encoding="utf-8", errors="replace")
    except: return None

def smart_norm(text, ag_name, level_str):
    """Replace agent-specific strings with canonical placeholders using word-boundary regex."""
    if text is None: return None
    ag_engine = f"{ag_name}_engine"
    ag_tools  = f"{ag_name}_tools"
    text = text.replace(ag_engine, "AGENT_ENGINE")
    text = text.replace(ag_tools,  "AGENT_TOOLS")
    text = re.sub(r'\b' + re.escape(ag_name) + r'\b', 'AGENT_ID', text)
    text = re.sub(r'(?<![a-zA-Z0-9])' + re.escape(level_str) + r'(?![a-zA-Z0-9])', 'LEVEL', text)
    return text

def compare(f1, f2, label):
    t1 = read(f1); t2 = read(f2)
    if t1 is None and t2 is None: return "BOTH_MISSING"
    if t1 is None: return f"A1_MISSING" if str(f1).count("agent_a1") > str(f1).count("agent_a2") else "MISSING"
    if t2 is None: return f"A2_MISSING" if str(f2).count("agent_a2") > str(f2).count("agent_a1") else "MISSING"
    if t1 == t2: return "IDENTICAL"
    # Normalize and check
    n1 = smart_norm(t1, "agent_a1", "a1")
    n2 = smart_norm(t2, "agent_a2", "a2")
    if n1 == n2: return "NAME_ONLY"
    return f"REAL_DIFF ({len(t1.splitlines())}L vs {len(t2.splitlines())}L)"

# Map files
for agent_dir, agent_name, level_str in [(A1,"agent_a1","a1"),(A2,"agent_a2","a2"),(A3,"agent_a3","a3")]:
    agent_dir.mkdir(parents=True, exist_ok=True)

# Collect all relative paths that exist in any agent
all_rels = set()
for base, name in [(A1,"agent_a1"),(A2,"agent_a2"),(A3,"agent_a3")]:
    for p in base.rglob("*"):
        if "__pycache__" in str(p): continue
        if p.is_file():
            rel = str(p.relative_to(base))
            # Normalize rel to agent_a1 naming
            rel = rel.replace("agent_a2", "agent_a1").replace("agent_a3", "agent_a1").replace("a2","a1").replace("a3","a1")
            all_rels.add(rel)

print("=" * 72)
print("  THREE-WAY DIFF: agent_a1 vs agent_a2 vs agent_a3")
print("=" * 72)
print()

# Build results table
rows = []
for rel in sorted(all_rels):
    # Map rel back to each agent's actual filename
    def actual(base, agent_dir_name, rel_norm):
        return base / rel_norm.replace("agent_a1_engine", f"{agent_dir_name}_engine") \
                               .replace("agent_a1_tools", f"{agent_dir_name}_tools")

    p1 = actual(A1, "agent_a1", rel)
    p2 = actual(A2, "agent_a2", rel)
    p3 = actual(A3, "agent_a3", rel)

    r12 = "?"; r13 = "?"
    if p1.exists() and p2.exists():
        r12 = compare(p1, p2, f"{rel} a1->a2")
    elif p1.exists() and not p2.exists():
        r12 = "A2_MISSING"
    elif not p1.exists() and p2.exists():
        r12 = "A1_MISSING"
    else:
        r12 = "BOTH_MISSING"

    if p1.exists() and p3.exists():
        r13 = compare(p1, p3, f"{rel} a1->a3")
    elif p1.exists() and not p3.exists():
        r13 = "A3_MISSING"
    elif not p1.exists() and p3.exists():
        r13 = "A1_MISSING"
    else:
        r13 = "BOTH_MISSING"

    rows.append((rel, r12, r13,
                 len(read(p1).splitlines()) if read(p1) else 0,
                 len(read(p2).splitlines()) if read(p2) else 0,
                 len(read(p3).splitlines()) if read(p3) else 0))

# Group by status
identical_all  = []  # IDENTICAL or NAME_ONLY for both
identical_12   = []  # a1==a2 but different from a3 or a3 missing
identical_13   = []
real_diffs     = []
missing_files  = []

for rel, r12, r13, l1, l2, l3 in rows:
    both_ok = r12 in ("IDENTICAL", "NAME_ONLY") and r13 in ("IDENTICAL", "NAME_ONLY")
    if both_ok:
        identical_all.append((rel, r12, l1, l2, l3))
    elif r12 in ("IDENTICAL", "NAME_ONLY") and r13 not in ("IDENTICAL", "NAME_ONLY"):
        identical_12.append((rel, r13, l1, l2, l3))
    elif r13 in ("IDENTICAL", "NAME_ONLY") and r12 not in ("IDENTICAL", "NAME_ONLY"):
        identical_13.append((rel, r12, l1, l2, l3))
    elif "MISSING" in str(r12) or "MISSING" in str(r13):
        missing_files.append((rel, r12, r13, l1, l2, l3))
    else:
        real_diffs.append((rel, r12, r13, l1, l2, l3))

print(f"IDENTICAL across all 3 agents ({len(identical_all)} files):")
for rel, status, l1, l2, l3 in identical_all:
    print(f"  = {rel:50s}  ({l1}L)")

if identical_12:
    print(f"\na1==a2 but a3 differs/missing ({len(identical_12)} files):")
    for rel, r13, l1, l2, l3 in identical_12:
        print(f"  ~ {rel:50s}  a1={l1}L a2={l2}L a3={l3}L  a1->a3: {r13}")

if identical_13:
    print(f"\na1==a3 but a2 differs/missing ({len(identical_13)} files):")
    for rel, r12, l1, l2, l3 in identical_13:
        print(f"  ~ {rel:50s}  a1={l1}L a2={l2}L a3={l3}L  a1->a2: {r12}")

if missing_files:
    print(f"\nMISSING ({len(missing_files)} files):")
    for rel, r12, r13, l1, l2, l3 in missing_files:
        print(f"  x {rel:50s}  a1={l1}L a2={l2}L a3={l3}L  a1->a2: {r12}  a1->a3: {r13}")

print(f"\nREAL DIFFERENCES beyond name substitution ({len(real_diffs)} files):")
for rel, r12, r13, l1, l2, l3 in real_diffs:
    # Check if the diff is actually a pure name substitution that our regex missed
    t1 = read(actual(A1, "agent_a1", rel))
    t2 = read(actual(A2, "agent_a2", rel))
    # Try more aggressive normalization
    if t1 and t2:
        n1 = t1; n2 = t2
        for src, dst in [("agent_a1","AGENT"),("agent_a2","AGENT"),("agent_a3","AGENT"),
                         ("a1","X"),("a2","X"),("a3","X")]:
            n1 = re.sub(r'\b' + re.escape(src) + r'\b', dst, n1)
            n2 = re.sub(r'\b' + re.escape(src) + r'\b', dst, n2)
        if n1 == n2:
            print(f"  N {rel:50s}  (aggressive normalization PASSES — name only)")
            continue
    print(f"  R {rel:50s}  a1={l1}L a2={l2}L a3={l3}L  a1->a2: {r12}  a1->a3: {r13}")

print()
print("=" * 72)
print("  VERDICT")
print("=" * 72)

# Count total
total = len(rows)
ok_count = len(identical_all) + len(identical_12) + len(identical_13)
real_count = len(real_diffs)
missing_count = len(missing_files)

# Quick byte-level check of the real_diffs
truly_different = []
for rel, r12, r13, l1, l2, l3 in real_diffs:
    p1 = actual(A1, "agent_a1", rel)
    p2 = actual(A2, "agent_a2", rel)
    p3 = actual(A3, "agent_a3", rel)
    t1 = read(p1) or ""; t2 = read(p2) or ""; t3 = read(p3) or ""
    if t1 == t2 == t3:
        continue  # shouldn't happen but be safe
    if t1 == t2 and t2 != t3:
        truly_different.append((rel, "a3 differs from a1/a2"))
    elif t1 == t3 and t2 != t1:
        truly_different.append((rel, "a2 differs from a1/a3"))
    elif t2 == t3 and t1 != t2:
        truly_different.append((rel, "a1 differs from a2/a3"))
    elif t1 != t2 and t2 != t3 and t1 != t3:
        truly_different.append((rel, "ALL THREE DIFFERENT"))
    else:
        truly_different.append((rel, "mixed"))

if truly_different:
    print(f"\nTruly different files ({len(truly_different)}):")
    for rel, desc in truly_different:
        print(f"  {desc:30s}  {rel}")

print(f"\nTotal files: {total}")
print(f"  Structurally identical: {ok_count} (name-substitution only)")
print(f"  Real differences:      {real_count}")
print(f"  Missing:               {missing_count}")
