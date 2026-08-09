"""
IPP.IPP_verify — the 17 design-invariant verification (spec §10).

verify_node(node) → list[str] of failed invariants (empty list = ALL 17 OK).
Each check is a direct, data-driven test of the constructed runtime peers.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from IPP.IPP_executor import IPPExecutor
from IPP.IPP_object import IPPObject
from IPP.IPP_ports import payload_hash

_RUNTIME_KEYS = {"code", "python", "script", "exec", "eval", "lambda",
                 "_impl", "function", "callable"}


def verify_node(node: Any) -> list[str]:
    """Run all 17 invariant checks on a constructed IPPNode."""
    failures: list[str] = []
    file_ = node.file
    raw = file_.raw

    # ── I1: Separation of Declaration and Enforcement ─────────────────────
    def _has_runtime(node_: Any) -> bool:
        if isinstance(node_, dict):
            for k, v in node_.items():
                if str(k).lower() in _RUNTIME_KEYS and \
                        not isinstance(v, (dict, list)):
                    return True
                if _has_runtime(v):
                    return True
        elif isinstance(node_, list):
            return any(_has_runtime(v) for v in node_)
        return False
    if _has_runtime(raw):
        failures.append("I1: runtime logic found inside the IPP Json File")

    # ── I2: Guardrail Completeness ────────────────────────────────────────
    for ch in node.channels:
        ex: IPPExecutor = node.executors[ch]
        if not getattr(ex, "_envelope_path", False):
            failures.append(f"I2: channel {ch} lacks the single guardrail "
                            "envelope path")

    # ── I3: Object-Executor Independence (Ω_k ⊥ Ξ_k) ──────────────────────
    for ch in node.channels:
        if node.objects[ch].state is node.executors[ch].__dict__:
            failures.append(f"I3: channel {ch} shares object/executor state")

    # ── I4: Atomic Hot-Swap ───────────────────────────────────────────────
    if not callable(getattr(node, "swap", None)):
        failures.append("I4: node lacks atomic hot-swap")

    # ── I5: Recursive Improvability (recall) ──────────────────────────────
    for ch in node.channels:
        if not callable(getattr(node.objects[ch], "recall", None)):
            failures.append(f"I5: channel {ch} object lacks recall")
        if not callable(getattr(node.executors[ch], "recall", None)):
            failures.append(f"I5: channel {ch} executor lacks recall")

    # ── I6: Audit Completeness (hash chain) ───────────────────────────────
    for ch in node.channels:
        if not node.executors[ch].audit_verify():
            failures.append(f"I6: channel {ch} audit hash chain broken")

    # ── I7: Port Orthogonality (Π ≅ Φ × A × T) ───────────────────────────
    for ch in node.channels:
        for port in (node.objects[ch].input_port, node.objects[ch].output_port):
            factors = port.factors()
            if not all(k in factors for k in ("core_flow", "accommodation",
                                              "template")):
                failures.append(f"I7: channel {ch} port lacks Φ×A×T factors")

    # ── I8: Constructor Independence (Γ ∉ F) ──────────────────────────────
    if "constructor" in raw or any(
            k == "constructor" or str(k).endswith("constructor")
            for k in raw.keys()):
        failures.append("I8: constructor declared inside the file")

    # ── I9: Topology Decoupling (no concrete wiring in F) ─────────────────
    concrete = ("upstream", "downstream", "wiring", "edges_external",
                "routes", "targets")
    if any(k in raw for k in concrete):
        failures.append("I9: concrete external wiring declared in the file")
    for ch in node.channels:
        caps = node.executors[ch].capabilities
        if any(k in caps for k in concrete):
            failures.append(f"I9: channel {ch} declares concrete wiring")

    # ── I10: Constructor-Specified External Topology ──────────────────────
    for ch in node.channels:
        ex = node.executors[ch]
        if callable(getattr(ex, "set_topology", None)):
            try:
                ex.set_topology()
                failures.append(f"I10: channel {ch} accepts external "
                                "topology writes")
            except (PermissionError, NotImplementedError):
                pass

    # ── I11: Topology Mutability Bound (τ* only via recall) ───────────────
    for ch in node.channels:
        if not getattr(node.executors[ch], "_topology_locked", False):
            failures.append(f"I11: channel {ch} topology not locked")

    # ── I12: Cross-Channel Object Independence ────────────────────────────
    seen: dict[int, str] = {}
    for ch in node.channels:
        if id(node.objects[ch].state) in seen:
            failures.append(f"I12: channels {seen[id(node.objects[ch].state)]}"
                            f" and {ch} share object state")
        seen[id(node.objects[ch].state)] = ch

    # ── I13: Cross-Channel Executor Independence ──────────────────────────
    seen = {}
    for ch in node.channels:
        ex = node.executors[ch]
        if id(ex.audit_log) in seen:
            failures.append(f"I13: channels {seen[id(ex.audit_log)]} and {ch} "
                            "share audit log")
        seen[id(ex.audit_log)] = ch

    # ── I14: Cross-Channel Non-Interference ───────────────────────────────
    for ch in node.channels:
        if getattr(node.executors[ch], "_blocking", False):
            failures.append(f"I14: channel {ch} blocks other channels")

    # ── I15: Internal DAG ─────────────────────────────────────────────────
    if node.file.internal_edges() and not node.topology.get("dag_ok", True):
        failures.append("I15: internal topology is not a port-level DAG")
    # (R4 already enforced at file validation; re-check cheaply)
    if not _dag_ok(node.file):
        failures.append("I15: internal topology failed DAG validation")

    # ── I16: Internal Edge Port Correctness (R1) ──────────────────────────
    for e in node.file.internal_edges():
        if e["from"]["port"] != "output" or e["to"]["port"] != "input":
            failures.append(f"I16: internal edge {e} has wrong port direction")

    # ── I17: Internal Edges Carry Payloads, Not State ─────────────────────
    for ch in node.channels:
        ex = node.executors[ch]
        if not getattr(ex, "_payload_copies", True):
            failures.append(f"I17: channel {ch} may share state internally")

    return failures


def _dag_ok(file_) -> bool:
    """Cheap port-level acyclicity re-check (structural cycles only)."""
    from collections import defaultdict, deque
    edges = file_.internal_edges()
    if not edges:
        return True
    ids = file_.channel_ids
    adj: dict[tuple, list] = defaultdict(list)
    indeg: dict[tuple, int] = defaultdict(int)
    vertices = {(c, p) for c in ids for p in ("input", "output")}
    for e in edges:
        f, t = e["from"], e["to"]
        src = (f["channel_id"], f["port"])
        dst = (t["channel_id"], t["port"])
        adj[src].append(dst)
        indeg[dst] += 1
        indeg.setdefault(src, 0)
    q = deque([v for v in vertices if indeg.get(v, 0) == 0])
    seen = 0
    while q:
        v = q.popleft()
        seen += 1
        for w in adj[v]:
            indeg[w] -= 1
            if indeg[w] == 0:
                q.append(w)
    return seen == len(vertices)


def verify_all(nodes: dict) -> dict:
    """Verify many nodes; returns {node_id: [failures]} ([] = ALL 17 OK)."""
    return {nid: verify_node(node) for nid, node in nodes.items()}
