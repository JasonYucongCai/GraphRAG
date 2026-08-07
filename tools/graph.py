"""
tools.graph — the Knowledge Graph Protocol (KGP).

Implements the global knowledge graph with:

  • Nodes   — knowledge units (subjects, papers, concepts) with rich metadata
  • Edges   — typed, directed; stored bidirectionally per the §4.3a invariant
              ∀X,Y: Y ∈ X.output ⇔ X ∈ Y.input
  • Local graphs — materialize the depth-k ego network of any node (default 3)
  • Traversal — BFS/DFS with relation filters (matching KGP traverse())
  • Analytics — PageRank (power iteration), in/out degree, community stats
  • Persistence — JSON store (registry + nodes + edges), backward compatible
    with the ScientificInfrastructure structurelist.json / input/output.json

This is the Layer-0 (global graph) and Layer-1 (local graphs) of the network.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

from tools.config import Config

logger = logging.getLogger("tools.graph")

RELATION_VOCAB = {
    "feeds_into", "depends_on", "example_of", "generalizes", "described_by",
    "formulated_by", "applied_in", "related_to", "contains", "used_in",
    "extends", "splits_from", "supersedes", "cites", "evidence_for",
    "lesson_from", "part_of", "dual_to", "uses",
    "describes", "implements", "driven_by", "enables", "reviews", "defines",
    "evaluates", "benchmarks", "evaluated_by",
    # domain relations shared by the survey projects (build_cy3 / build_multiagent)
    "introduces", "surveys", "exemplifies", "founds",
}


# ══════════════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class KGNode:
    node_id: Any
    entryname: str
    category: str = "subject"          # subject | paper | concept | note | experience
    description: str = ""
    content: dict = field(default_factory=dict)     # info/notebook/chunks refs
    embedding_ref: Optional[str] = None
    stats: dict = field(default_factory=dict)        # in_degree/out_degree/pagerank
    timestamps: dict = field(default_factory=dict)
    version: str = "v1.0"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "KGNode":
        d = dict(d)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class KGEdge:
    edge_id: str
    source: Any
    target: Any
    relation: str = "related_to"
    weight: float = 1.0
    evidence: list = field(default_factory=list)
    temporal: dict = field(default_factory=dict)
    agent_run: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "KGEdge":
        d = dict(d)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class LocalGraph:
    """A materialized depth-k ego network — the agent's working memory."""

    anchor: Any
    depth: int
    nodes: dict[Any, KGNode] = field(default_factory=dict)
    edges: list[KGEdge] = field(default_factory=list)
    paths: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    summaries: dict = field(default_factory=dict)     # community summaries

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict:
        return {
            "anchor": self.anchor,
            "depth": self.depth,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "paths": self.paths,
            "stats": self.stats,
            "summaries": self.summaries,
        }

    def verbalize(self, max_nodes: int = 200, max_edges: int = 300) -> str:
        """Graph-to-text: compact triple list for LLM prompts (§7.5)."""
        lines = [f"[Local graph of {self.anchor} at depth {self.depth}]"]
        nodes = list(self.nodes.values())[:max_nodes]
        edges = list(self.edges)[:max_edges]
        lines.append(f"nodes ({len(nodes)} shown):")
        for n in nodes:
            lines.append(f"  - {n.entryname} [{n.category}] {n.description[:120]}")
        lines.append("edges:")
        for e in edges:
            s = self.nodes[e.source].entryname if e.source in self.nodes else e.source
            t = self.nodes[e.target].entryname if e.target in self.nodes else e.target
            lines.append(f"  - {s} --[{e.relation}]--> {t}")
        if self.stats:
            lines.append(f"stats: {self.stats}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# KnowledgeGraph — the global graph (KGP)
# ══════════════════════════════════════════════════════════════════════════════


class KnowledgeGraph:
    """
    The global graph G = (V, E, X).

    Backward compatible with the ScientificInfrastructure:
      • registry mirrors structurelist.json (folderid ↔ entryname)
      • edges mirror input.json / output.json with §4.3a bidirectional rule
    """

    def __init__(self, path: Optional[Path] = None, auto_load: bool = True):
        self.path: Path = path or Config.GRAPH_JSON
        self._nodes: dict[Any, KGNode] = {}
        self._edges: dict[str, KGEdge] = {}
        self._adjacency: dict[Any, list[str]] = defaultdict(list)
        self._runs: list[dict] = []
        if auto_load and self.path.exists():
            self.load()

    # ── Node CRUD ─────────────────────────────────────────────────────────
    def add_node(
        self,
        node_id: Any,
        entryname: str,
        category: str = "subject",
        description: str = "",
        content: Optional[dict] = None,
        **meta,
    ) -> KGNode:
        if node_id in self._nodes:
            raise ValueError(f"node already exists: {node_id}")
        node = KGNode(
            node_id=node_id,
            entryname=entryname,
            category=category,
            description=description,
            content=content or {},
            timestamps={"created": time.strftime("%Y-%m-%d")},
            **meta,
        )
        self._nodes[node_id] = node
        self._recompute_stats()
        return node

    def get_node(self, node_id: Any) -> Optional[KGNode]:
        return self._nodes.get(node_id)

    def find_node(self, name_or_id: Any) -> Optional[KGNode]:
        """Resolve by id or by exact entryname match."""
        if name_or_id in self._nodes:
            return self._nodes[name_or_id]
        for n in self._nodes.values():
            if n.entryname.lower() == str(name_or_id).lower():
                return n
        return None

    def resolve(self, ref: Any) -> Any:
        """Resolve a node reference (id or entryname) to its node_id."""
        node = self.find_node(ref)
        return node.node_id if node else None

    def update_node(self, node_id: Any, **fields) -> Optional[KGNode]:
        node = self._nodes.get(node_id)
        if node is None:
            return None
        for k, v in fields.items():
            if hasattr(node, k):
                setattr(node, k, v)
        node.timestamps["updated"] = time.strftime("%Y-%m-%d")
        self._recompute_stats()
        return node

    def remove_node(self, node_id: Any) -> bool:
        if node_id not in self._nodes:
            return False
        # remove all touching edges bidirectionally
        for eid in list(self._adjacency.get(node_id, [])):
            self.remove_edge(eid)
        del self._nodes[node_id]
        self._adjacency.pop(node_id, None)
        self._recompute_stats()
        return True

    # ── Edge CRUD (with §4.3a bidirectional consistency) ─────────────────
    def add_edge(
        self,
        source: Any,
        target: Any,
        relation: str = "related_to",
        weight: float = 1.0,
        evidence: Optional[list] = None,
        agent_run: str = "",
        **meta,
    ) -> KGEdge:
        """Add an edge. Enforces: both endpoints exist and relation in vocab."""
        if source not in self._nodes:
            raise ValueError(f"source node not found: {source}")
        if target not in self._nodes:
            raise ValueError(f"target node not found: {target}")
        if relation not in RELATION_VOCAB:
            logger.warning("relation '%s' not in vocab; adding anyway", relation)
        if self.has_edge(source, target, relation):
            return self._edges[self._find_edge(source, target, relation)]
        eid = f"e{len(self._edges) + 1}-{source}-{target}"
        edge = KGEdge(
            edge_id=eid, source=source, target=target, relation=relation,
            weight=weight, evidence=evidence or [],
            temporal={"valid_from": time.strftime("%Y-%m-%d")}, agent_run=agent_run,
            **meta,
        )
        self._edges[eid] = edge
        self._adjacency[source].append(eid)
        self._adjacency[target].append(eid)
        self._recompute_stats()
        return edge

    def has_edge(self, source: Any, target: Any, relation: str) -> bool:
        return self._find_edge(source, target, relation) is not None

    def _find_edge(self, source: Any, target: Any, relation: str) -> Optional[str]:
        for eid in self._adjacency.get(source, []):
            e = self._edges[eid]
            if e.target == target and e.relation == relation:
                return eid
        return None

    def remove_edge(self, edge_id: str) -> bool:
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            return False
        for nid in (edge.source, edge.target):
            if edge_id in self._adjacency.get(nid, []):
                self._adjacency[nid].remove(edge_id)
        self._recompute_stats()
        return True

    def neighbors(self, node_id: Any, relation_filter: Optional[str] = None) -> list[tuple[Any, str, str]]:
        """Return (neighbor_id, edge_id, relation) for both in/out edges."""
        out = []
        for eid in self._adjacency.get(node_id, []):
            e = self._edges[eid]
            if relation_filter and e.relation != relation_filter:
                continue
            nbr = e.target if e.source == node_id else e.source
            out.append((nbr, eid, e.relation))
        return out

    def outgoing(self, node_id: Any) -> list[tuple[Any, str]]:
        """(target, relation) pairs for edges leaving node_id."""
        return [
            (e.target, e.relation)
            for eid in self._adjacency.get(node_id, [])
            for e in [self._edges[eid]]
            if e.source == node_id
        ]

    def incoming(self, node_id: Any) -> list[tuple[Any, str]]:
        """(source, relation) pairs for edges entering node_id."""
        return [
            (e.source, e.relation)
            for eid in self._adjacency.get(node_id, [])
            for e in [self._edges[eid]]
            if e.target == node_id
        ]

    # ── Bidirectional consistency validator (§4.3a) ──────────────────────
    def validate_consistency(self) -> list[str]:
        """
        Verify the §4.3a invariant in its storage form: every directed edge is
        stored ONCE and its two halves agree. For ∀X,Y: Y ∈ X.output ⇔
        X ∈ Y.input, the graph must satisfy:
          1. both endpoints exist in the node registry
          2. the edge is reachable from BOTH adjacency lists (source and target)
          3. no dangling references in the registry
        Returns a list of violations (empty = consistent).
        """
        violations: list[str] = []
        for eid, e in self._edges.items():
            if e.source not in self._nodes:
                violations.append(f"edge {eid}: source {e.source} missing from registry")
            if e.target not in self._nodes:
                violations.append(f"edge {eid}: target {e.target} missing from registry")
            if eid not in self._adjacency.get(e.source, []):
                violations.append(f"edge {eid}: missing from {e.source}/output.json view")
            if eid not in self._adjacency.get(e.target, []):
                violations.append(f"edge {eid}: missing from {e.target}/input.json view")
        for nid, eids in self._adjacency.items():
            if nid not in self._nodes:
                violations.append(f"adjacency for missing node {nid}")
            for eid in eids:
                if eid not in self._edges:
                    violations.append(f"adjacency references unknown edge {eid}")
        return violations

    # ── Local graph materialization: depth-k ego network (Layer 1) ───────
    def materialize_local(
        self,
        anchor: Any,
        depth: int = 3,
        relation_filter: Optional[str] = None,
        include_shortcuts: bool = True,
    ) -> LocalGraph:
        """
        Materialize L_k(anchor) = induced subgraph over nodes within k hops.

        BFS in both directions (undirected hops), then keep ALL internal edges
        (shortcuts) so the agent sees the full relational structure.
        O(V + E) — matching the KGP traverse() complexity.
        """
        anchor = self.resolve(anchor)
        if anchor is None:
            raise KeyError(f"anchor not found: {anchor}")

        visited: set[Any] = {anchor}
        frontier = {anchor}
        levels: dict[Any, int] = {anchor: 0}

        for d in range(1, depth + 1):
            nxt = set()
            for node in frontier:
                for nbr, _, _ in self.neighbors(node, relation_filter):
                    if nbr not in visited:
                        visited.add(nbr)
                        levels[nbr] = d
                        nxt.add(nbr)
            if not nxt:
                break
            frontier = nxt

        local = LocalGraph(anchor=anchor, depth=depth)
        for nid in visited:
            local.nodes[nid] = self._nodes[nid]

        seen: set[str] = set()
        for eid, e in self._edges.items():
            if e.source in visited and e.target in visited:
                if include_shortcuts or (
                    abs(levels.get(e.source, 0) - levels.get(e.target, 0)) <= 1
                ):
                    if eid not in seen:
                        local.edges.append(e)
                        seen.add(eid)

        # shortest paths from anchor to every other node (for path reasoning)
        local.paths = self.shortest_paths(anchor, list(visited - {anchor}))
        local.stats = self.local_stats(local)
        return local

    def local_stats(self, local: LocalGraph) -> dict:
        n = local.node_count()
        m = local.edge_count()
        return {
            "n": n,
            "m": m,
            "density": (2 * m / (n * (n - 1))) if n > 1 else 0.0,
            "diameter": max((len(p) - 1) for p in local.paths) if local.paths else 0,
        }

    def shortest_paths(self, source: Any, targets: Iterable[Any]) -> list[list[Any]]:
        """BFS shortest paths from source to each target (unweighted)."""
        source = self.resolve(source)
        result = []
        for t in targets:
            t = self.resolve(t)
            if t is None or t == source:
                continue
            path = self.bfs_path(source, t)
            if path:
                result.append(path)
        return result

    def bfs_path(self, source: Any, target: Any) -> Optional[list[Any]]:
        """Single-pair BFS shortest path."""
        if source not in self._nodes or target not in self._nodes:
            return None
        prev: dict[Any, Any] = {source: None}
        q = deque([source])
        while q:
            cur = q.popleft()
            if cur == target:
                path = []
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                return path[::-1]
            for nbr, _, _ in self.neighbors(cur):
                if nbr not in prev:
                    prev[nbr] = cur
                    q.append(nbr)
        return None

    # ── Analytics ─────────────────────────────────────────────────────────
    def _recompute_stats(self) -> None:
        in_deg: dict[Any, int] = defaultdict(int)
        out_deg: dict[Any, int] = defaultdict(int)
        for e in self._edges.values():
            out_deg[e.source] += 1
            in_deg[e.target] += 1
        for nid, node in self._nodes.items():
            node.stats["in_degree"] = in_deg.get(nid, 0)
            node.stats["out_degree"] = out_deg.get(nid, 0)

    def pagerank(self, damping: float = 0.85, iters: int = 50, tol: float = 1e-6) -> dict[Any, float]:
        """Power-iteration PageRank over the undirected-view graph."""
        nodes = list(self._nodes)
        n = len(nodes)
        if n == 0:
            return {}
        pr = {x: 1.0 / n for x in nodes}
        # neighbors as undirected sets
        undir: dict[Any, set[Any]] = {x: set() for x in nodes}
        for e in self._edges.values():
            undir[e.source].add(e.target)
            undir[e.target].add(e.source)
        for _ in range(iters):
            new_pr = {}
            dangling = (1.0 - damping) / n
            for x in nodes:
                s = sum(pr[y] / max(1, len(undir[y])) for y in undir[x])
                new_pr[x] = dangling + damping * s
            diff = sum(abs(new_pr[x] - pr[x]) for x in nodes)
            pr = new_pr
            if diff < tol:
                break
        for nid, score in pr.items():
            if nid in self._nodes:
                self._nodes[nid].stats["pagerank"] = round(score, 6)
        return pr

    def connected_components(self) -> list[list[Any]]:
        """Weakly-connected components."""
        seen: set[Any] = set()
        comps = []
        for start in self._nodes:
            if start in seen:
                continue
            comp, q = [start], deque([start])
            seen.add(start)
            while q:
                cur = q.popleft()
                for nbr, _, _ in self.neighbors(cur):
                    if nbr not in seen:
                        seen.add(nbr)
                        comp.append(nbr)
                        q.append(nbr)
            comps.append(comp)
        return comps

    def density(self) -> float:
        n = len(self._nodes)
        m = len(self._edges)
        return (2 * m / (n * (n - 1))) if n > 1 else 0.0

    def summary(self) -> str:
        pr = self.pagerank()
        comps = self.connected_components()
        top = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:6]
        lines = [
            f"KnowledgeGraph: {len(self._nodes)} nodes, {len(self._edges)} edges",
            f"density={self.density():.4f}  components={len(comps)}",
        ]
        for nid, score in top:
            name = self._nodes[nid].entryname if nid in self._nodes else nid
            lines.append(f"  pagerank[{name}]={score:.4f}")
        return "\n".join(lines)

    # ── Persistence (JSON, backward compatible) ───────────────────────────
    def save(self, path: Optional[Path] = None) -> Path:
        target = path or self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "meta": {"saved": time.strftime("%Y-%m-%dT%H:%M:%S"), "version": "kgp-1.0"},
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
            "runs": self._runs,
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.info("graph saved: %s (%d nodes, %d edges)", target, len(self._nodes), len(self._edges))
        return target

    def load(self, path: Optional[Path] = None) -> None:
        source = path or self.path
        if not source.exists():
            logger.warning("graph file not found: %s", source)
            return
        payload = json.loads(source.read_text(encoding="utf-8"))
        self._nodes = {
            n["node_id"]: KGNode.from_dict(n) for n in payload.get("nodes", [])
        }
        self._edges = {
            e["edge_id"]: KGEdge.from_dict(e) for e in payload.get("edges", [])
        }
        self._adjacency = defaultdict(list)
        for e in self._edges.values():
            self._adjacency[e.source].append(e.edge_id)
            self._adjacency[e.target].append(e.edge_id)
        self._runs = payload.get("runs", [])
        self._recompute_stats()
        logger.info("graph loaded: %s (%d nodes, %d edges)", source, len(self._nodes), len(self._edges))

    # ── Run log ───────────────────────────────────────────────────────────
    def log_run(self, run: dict) -> None:
        run.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._runs.append(run)
        if len(self._runs) > 500:
            self._runs = self._runs[-500:]

    def runs(self) -> list[dict]:
        return list(self._runs)

    # ── Registry helpers (backward compat with structurelist.json) ───────
    def to_structurelist(self) -> list[dict]:
        """Emit the ScientificInfrastructure structurelist.json format."""
        out = []
        for nid, node in sorted(self._nodes.items(), key=lambda kv: _sort_key(kv[0])):
            out.append({"folderid": nid, "entryname": node.entryname})
        return out

    def to_edges_files(self) -> dict[Any, dict[str, list[dict]]]:
        """Emit per-node input.json/output.json format (backward compatible)."""
        result: dict[Any, dict[str, list[dict]]] = {}
        for nid in self._nodes:
            outs = [
                {"outputid": t, "entryname": self._nodes[t].entryname if t in self._nodes else str(t)}
                for t, _ in self.outgoing(nid)
            ]
            ins = [
                {"inputeid": s, "entryname": self._nodes[s].entryname if s in self._nodes else str(s)}
                for s, _ in self.incoming(nid)
            ]
            result[nid] = {"input.json": ins, "output.json": outs}
        return result


def _sort_key(x: Any):
    """Sort node ids: ints numerically, strings alphabetically."""
    return (0, x) if isinstance(x, int) else (1, str(x))
