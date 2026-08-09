"""
IPP.IPP_file — the IPP Json File (F): static, declarative specification.

Implements §2 of IPP_v0.2.8_Specification.md:

  F ::= { "$schema", "ipp_version", "node_id",
          "channels": [channel₁..channelₙ],
          "internal_topology"? }

Responsibilities:
  • parse + validate against the formal schema (jsonschema)
  • per-channel accessors (ports, process, executor decl, handler ref)
  • internal-topology validation: rules R1–R4 (§2.1)
      R1 direction  — from.port = "output", to.port = "input"
      R2 distinct   — from.channel_id ≠ to.channel_id
      R3 valid refs — every channel_id exists in channels
      R4 acyclicity — G_int is a port-level DAG
  • Invariant I1 — F contains declarations only (no runtime logic)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from IPP.IPP_schema import IPP_JSON_SCHEMA, IPP_SCHEMA_URI, IPP_VERSION

logger = logging.getLogger("IPP.IPP_file")

# Keys that would smuggle runtime logic into F (I1 violation)
_RUNTIME_KEYS = {"code", "python", "script", "exec", "eval", "lambda",
                 "_impl", "function", "callable"}


class IPPValidationError(ValueError):
    """Raised when an IPP Json File is malformed or violates R1–R4 / I1."""


class IPPFile:
    """A validated IPP v0.2.8 Json File (F)."""

    def __init__(self, raw: dict, path: Optional[Path] = None):
        self.raw: dict = raw
        self.path: Optional[Path] = path
        self.node_id: str = raw.get("node_id", "")
        self.channels: list[dict] = raw.get("channels", [])
        self.internal_topology: dict = raw.get("internal_topology", {})
        self._channel_ids: Optional[list[str]] = None
        self._validate_schema()
        self._validate_no_runtime()
        self._validate_internal_topology()

    # ── loaders ───────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path) -> "IPPFile":
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(raw, path=p)

    @classmethod
    def from_dict(cls, raw: dict) -> "IPPFile":
        return cls(raw)

    # ── validation ────────────────────────────────────────────────────────
    def _validate_schema(self) -> None:
        try:
            import jsonschema
        except ImportError as exc:  # pragma: no cover
            raise IPPValidationError(
                "jsonschema required to validate IPP files") from exc
        try:
            jsonschema.validate(self.raw, IPP_JSON_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise IPPValidationError(f"IPP file invalid: {exc.message}") from exc
        ids = [c.get("channel_id") for c in self.channels]
        if len(set(ids)) != len(ids):
            raise IPPValidationError(
                f"duplicate channel_id in {self.node_id!r}: {ids}")

    def _validate_no_runtime(self) -> None:
        """Invariant I1 — F ∩ I = ∅: no runtime logic inside the file."""
        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if str(k).lower() in _RUNTIME_KEYS and not isinstance(v, (dict, list)):
                        raise IPPValidationError(
                            f"I1 violation: runtime key {k!r} in IPP file "
                            f"{self.node_id!r}")
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(self.raw)

    def _validate_internal_topology(self) -> None:
        edges = self.internal_topology.get("edges", [])
        ids = set(self.channel_ids)
        for e in edges:
            f, t = e.get("from", {}), e.get("to", {})
            # R1 direction
            if f.get("port") != "output" or t.get("port") != "input":
                raise IPPValidationError(
                    f"R1 violation in {self.node_id}: internal edge {e} "
                    "must go from output → input")
            # R2 distinct channels
            if f.get("channel_id") == t.get("channel_id"):
                raise IPPValidationError(
                    f"R2 violation in {self.node_id}: internal edge {e} "
                    "connects a channel to itself")
            # R3 valid references
            if f.get("channel_id") not in ids or t.get("channel_id") not in ids:
                raise IPPValidationError(
                    f"R3 violation in {self.node_id}: edge {e} references "
                    "an undeclared channel")
            # R4 acyclicity (port-level DAG) — check immediately
        self._check_dag(edges)

    def _check_dag(self, edges: list[dict]) -> None:
        """R4 — port-level DAG check (I15). Vertices are (channel, port)."""
        # A structural cycle exists iff some port reaches itself through
        # internal edges alone. Since edges always go (c, output)→(c', input)
        # with c ≠ c', a cycle needs a path output_a → input_b → (handler is
        # OUTSIDE G_int) — so by construction no path can leave an input port.
        # The only real cycle risk: two edges forming (a.out→b.in) and
        # (b.out→a.in) — still acyclic at port level (pipeline loop, §1.3).
        # We nevertheless run a strict topological check over the directed
        # graph of ports for completeness.
        from collections import defaultdict, deque
        adj: dict[tuple, list] = defaultdict(list)
        indeg: dict[tuple, int] = defaultdict(int)
        vertices = {(c, "input") for c in self.channel_ids} | \
                   {(c, "output") for c in self.channel_ids}
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
        if seen != len(vertices):
            raise IPPValidationError(
                f"R4 violation in {self.node_id}: internal topology is not "
                "a port-level DAG (structural cycle detected)")

    # ── accessors ─────────────────────────────────────────────────────────
    @property
    def channel_ids(self) -> list[str]:
        if self._channel_ids is None:
            self._channel_ids = [c["channel_id"] for c in self.channels]
        return self._channel_ids

    def channel(self, channel_id: str) -> dict:
        for c in self.channels:
            if c["channel_id"] == channel_id:
                return c
        raise KeyError(f"channel {channel_id!r} not in {self.node_id!r}")

    def object_decl(self, channel_id: str) -> dict:
        return self.channel(channel_id)["ipp_object"]

    def executor_decl(self, channel_id: str) -> dict:
        return self.channel(channel_id)["ipp_executor"]

    def handler_ref(self, channel_id: str) -> Optional[str]:
        return self.channel(channel_id).get("handler")

    def internal_edges(self) -> list[dict]:
        return self.internal_topology.get("edges", [])

    def summary(self) -> str:
        n = len(self.channels)
        edges = len(self.internal_edges())
        return (f"IPPFile({self.node_id}): {n} channel(s)"
                + (f" · {edges} internal edge(s)" if edges else ""))
