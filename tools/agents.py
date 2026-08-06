"""
tools.agents — agents that operate on nodes via local graphs (IPP).

  • NodeAgent    — operates ON a single node: materializes L_3(u), pulls
                   encoded content, runs a task using the local graph.
  • GrowthAgent  — the recursive self-improvement agent: external expansion
                   (register/link/dedup), internal self-evolving (consolidate,
                   infer, prune), external self-exploration (probe gaps).

Both are IPPs: (task) → Φ → (result). They orchestrate the AgentEngine with
graph-aware prompts and enforce the ScientificInfrastructure guardrails
(dedup, per-run limits, bidirectional consistency, version log).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from tools.config import Config
from tools.encoder import EncoderLayer
from tools.engine import AgentEngine
from tools.graph import KnowledgeGraph, LocalGraph
from tools.IPP import IPP, ToolResult

logger = logging.getLogger("tools.agents")

NODE_PROMPT = """You are a knowledge-graph agent working ON the node "{entryname}" ({node_id}).
Your working memory is its LOCAL GRAPH (depth-3 neighbors). Use get_local_graph
to see it, search_nodes for encoded content, read_node for details, and the
growth tools only when you have evidence. Answer concisely with facts grounded
in the local graph and retrieved chunks."""

GROWTH_PROMPT = """You are the GROWTH agent of a Graph Knowledge Network.
Your job is recursive self-improvement:
1. External expansion: find genuinely new topics around the anchor node; dedup
   (register_node checks), then link_nodes with justification.
2. Internal self-evolving: infer_edges (latent links), probe_gap (missing
   nodes), summarize_local (consolidation).
3. Validate: always run validate_graph before finishing.
Respect limits: ≤{max_subjects} new nodes per run. Never create duplicates.""" 


class NodeAgent(IPP):
    """
    The primary agent: operates on a node using its local graph (Layer 1–3).

    Flow (per §7.6 of the design notebook):
      L = materialize_local(u, 3) → ctx = encode_and_retrieve → agent reason →
      tools → answer with provenance.
    """

    name = "node-agent"

    def __init__(self, graph: KnowledgeGraph, encoder: EncoderLayer, llm=None,
                 model: Optional[str] = None):
        super().__init__()
        self.graph = graph
        self.encoder = encoder
        self.engine = AgentEngine(graph, encoder, llm=llm, model=model)
        self.name = "node-agent"

    def operate(self, node_ref: Any, task: str, verbose: bool = True) -> dict:
        """Run a task on `node_ref`, returning answer + trace summary."""
        anchor = self.graph.resolve(node_ref)
        if anchor is None:
            raise KeyError(f"node not found: {node_ref}")
        node = self.graph.get_node(anchor)

        # 1. Materialize the local graph (working memory)
        local = self.graph.materialize_local(anchor, depth=Config.LOCAL_DEPTH)
        # 2. Vector retrieval over the local graph
        hybrid = self.encoder.hybrid_search(task, self.graph, anchor,
                                            k=Config.VECTOR_TOP_K)
        # 2b. ground the task in the local graph + retrieved evidence
        evidence = []
        for chunk, sim in self.encoder.search(task, k=5, node_filter=anchor):
            evidence.append(f"[chunk {chunk.chunk_id} sim={sim:.3f}] {chunk.text[:220]}")
        for nid, sim in hybrid[:5]:
            n = self.graph.get_node(nid)
            if n:
                evidence.append(f"[node {n.entryname} score={sim:.3f}] {n.description[:180]}")
        grounded_task = (
            f"{task}\n\n"
            f"WORKING MEMORY — local graph of {node.entryname} (depth {Config.LOCAL_DEPTH}):\n"
            f"{local.verbalize(max_nodes=40, max_edges=50)}\n\n"
            f"RETRIEVED EVIDENCE (encoder layer):\n" + ("\n".join(evidence) or "(none)")
        )

        # 3. Bind engine to the node with a node-aware system prompt
        prompt = NODE_PROMPT.format(entryname=node.entryname, node_id=node.node_id)
        self.engine.system_prompt = prompt
        self.engine.bind_node(anchor)

        # 4. Run the agent loop
        events: list[dict] = []
        final = ""
        for event in self.engine.chat_stream(grounded_task, node_id=anchor):
            if verbose:
                if event.type in ("tool_call",):
                    pass
            events.append({"type": event.type, "tool": event.tool,
                           "content": (event.content or "")[:200]})
            if event.type == "text":
                final += event.content or ""
        final = final.strip()

        return {
            "node_id": anchor,
            "entryname": node.entryname,
            "task": task,
            "answer": final,
            "local_graph": {"n": local.node_count(), "m": local.edge_count(),
                            "stats": local.stats},
            "hybrid_evidence": [{"node": nid, "score": round(s, 4)}
                                for nid, s in hybrid[:5]],
            "trace": events,
            "tokens": self.engine._session_tokens,
        }

    # IPP wrapper
    def transform(self, inp: dict) -> dict:
        return self.operate(inp["node_ref"], inp["task"],
                            verbose=inp.get("verbose", False))


class GrowthAgent(IPP):
    """
    The recursive self-improvement agent (Layer 4).

    Implements:
      • external expansion  — propose+apply new nodes/edges (dedup + limits)
      • internal self-evolving — consolidation, inference, pruning
      • external self-exploration — gap probing
      • validation — §4.3a consistency + VCL run log
    """

    name = "growth-agent"

    def __init__(self, graph: KnowledgeGraph, encoder: EncoderLayer, llm=None,
                 model: Optional[str] = None):
        super().__init__()
        self.graph = graph
        self.encoder = encoder
        self.engine = AgentEngine(graph, encoder, llm=llm, model=model,
                                  system_prompt=GROWTH_PROMPT.format(
                                      max_subjects=Config.MAX_NEW_SUBJECTS_PER_RUN))
        self.name = "growth-agent"

    def expand(self, anchor_ref: Any, topic: str, motivation: str = "",
               verbose: bool = True) -> dict:
        """
        External expansion: grounded propose → apply pipeline.

        Stage 1 (propose): the LLM returns a STRUCTURED JSON growth proposal
            grounded in the anchor's local graph + encoder evidence.
        Stage 2 (apply): proposals are applied through the graph tools
            (dedup, per-run limits, bidirectional consistency, VCL run log).
        """
        anchor = self.graph.resolve(anchor_ref)
        if anchor is None:
            raise KeyError(f"anchor not found: {anchor_ref}")
        node = self.graph.get_node(anchor)

        # 1. probe gaps in the anchor's local graph
        local = self.graph.materialize_local(anchor, Config.LOCAL_DEPTH)
        gaps = self._probe(local)
        ctx_summary = local.verbalize(max_nodes=60, max_edges=80)
        evidence = []
        for chunk, sim in self.encoder.search(topic, k=6, node_filter=anchor):
            evidence.append(f"[chunk {chunk.chunk_id} sim={sim:.3f}] {chunk.text[:200]}")
        for nid, sim in self.encoder.search_nodes(topic, k=5):
            n = self.graph.get_node(nid)
            if n:
                evidence.append(f"[node {n.entryname} score={sim:.3f}] {n.description[:160]}")

        propose_prompt = (
            "You are the GROWTH agent of a Graph Knowledge Network. "
            "Ground your proposal ONLY in the provided context (do not invent "
            "papers or facts not in the context). "
            "Return STRICT JSON (no markdown fences) with schema:\n"
            "{\"new_nodes\": [{\"node_id\": str, \"entryname\": str, "
            "\"category\": \"concept\"|\"paper\", \"description\": str, "
            "\"links\": [{\"source\": str, \"target\": str, \"relation\": str}]}], "
            "\"new_edges\": [{\"source\": str, \"target\": str, \"relation\": str}]}\n"
            "Rules: max 3 new nodes; every source/target must be a node_id that "
            "exists OR is created in this same proposal; use only these relations: "
            "depends_on, extends, uses, part_of, example_of, related_to, "
            "describes, enables, feeds_into, cites, applied_in.\n\n"
            f"Anchor: {node.entryname} ({node.node_id})\n"
            f"Topic to explore: {topic}\nMotivation: {motivation}\n\n"
            f"LOCAL GRAPH:\n{ctx_summary}\n\n"
            f"ENCODER EVIDENCE:\n" + ("\n".join(evidence) or "(none)") + "\n\n"
            f"KNOWN GAPS: {gaps}"
        )
        proposal_raw = self.engine.llm.complete(
            system="You output JSON only. No explanations, no code fences.",
            user=propose_prompt,
            temperature=0.2,
        )
        proposal = self._parse_json_proposal(proposal_raw)

        # 2. apply through the graph tools (guardrails enforced here)
        applied_nodes, applied_edges, skipped, errors = self._apply_proposal(
            proposal, anchor)

        # 3. finalize: validate, run log, persist
        violations = self.graph.validate_consistency()
        run = {
            "agent": "growth",
            "anchor": anchor,
            "topic": topic,
            "proposal": proposal,
            "applied_nodes": applied_nodes,
            "applied_edges": applied_edges,
            "skipped": skipped,
            "errors": errors,
            "consistency_violations": len(violations),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.graph.log_run(run)
        self.graph.save()

        return {
            "proposal": proposal,
            "applied_nodes": applied_nodes,
            "applied_edges": applied_edges,
            "skipped": skipped,
            "errors": errors,
            "consistency_violations": len(violations),
            "gaps": gaps,
            "node_delta": len(applied_nodes),
        }

    # ── helpers ───────────────────────────────────────────────────────────
    def _parse_json_proposal(self, raw: str) -> dict:
        import re as _re
        text = raw.strip()
        text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.MULTILINE)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return {"new_nodes": [], "new_edges": []}
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            logger.warning("proposal JSON parse failed: %s", exc)
            return {"new_nodes": [], "new_edges": []}

    def _apply_proposal(self, proposal: dict, anchor: Any) -> tuple[list, list, list, list]:
        """Apply a growth proposal with dedup + limits + consistency."""
        applied_nodes: list[dict] = []
        applied_edges: list[dict] = []
        skipped: list[str] = []
        errors: list[str] = []

        # ── nodes ─────────────────────────────────────────────────────────
        new_nodes = proposal.get("new_nodes", [])[:Config.MAX_NEW_SUBJECTS_PER_RUN]
        created_ids: set[str] = set()
        for spec in new_nodes:
            nid = spec.get("node_id")
            name = spec.get("entryname")
            if not nid or not name:
                skipped.append(f"node spec missing node_id/entryname: {spec}")
                continue
            existing = self.graph.find_node(name)
            if existing is not None:
                skipped.append(f"dedup: '{name}' already exists as {existing.node_id}")
                continue
            if self.graph.get_node(nid) is not None:
                skipped.append(f"node id {nid} already exists")
                continue
            try:
                self.graph.add_node(
                    nid, name, category=spec.get("category", "concept"),
                    description=spec.get("description", ""),
                )
                created_ids.add(str(nid))
                applied_nodes.append({"node_id": nid, "entryname": name})
            except ValueError as exc:
                errors.append(str(exc))

        # ── edges (proposal links + explicit new_edges) ───────────────────
        def _try_link(s: str, t: str, rel: str, why: str = "") -> None:
            src, dst = self.graph.resolve(s), self.graph.resolve(t)
            if src is None:
                errors.append(f"edge skipped: source {s!r} not found")
                return
            if dst is None:
                errors.append(f"edge skipped: target {t!r} not found")
                return
            if self.graph.has_edge(src, dst, rel):
                skipped.append(f"edge exists: {s} --[{rel}]--> {t}")
                return
            self.graph.add_edge(src, dst, relation=rel,
                                evidence=[{"why": why}] if why else [],
                                agent_run="growth")
            applied_edges.append({"source": s, "target": t, "relation": rel})

        for spec in new_nodes:
            for link in spec.get("links", []):
                _try_link(link.get("source"), link.get("target"),
                          link.get("relation", "related_to"), link.get("why", ""))
        for spec in proposal.get("new_edges", []):
            _try_link(spec.get("source"), spec.get("target"),
                      spec.get("relation", "related_to"))

        return applied_nodes, applied_edges, skipped, errors

    def _probe(self, local: LocalGraph) -> list[str]:
        gaps = []
        if local.node_count() <= 1:
            gaps.append("anchor is isolated (no depth-3 neighbors)")
        comps = self.graph.connected_components()
        if len(comps) > 1:
            gaps.append(f"{len(comps)} weakly-connected components; bridge them")
        for n in local.nodes.values():
            if not n.description:
                gaps.append(f"node {n.node_id} ({n.entryname}) lacks a description")
        return gaps or ["none obvious — explore the topic anyway"]

    # IPP wrapper
    def transform(self, inp: dict) -> dict:
        return self.expand(inp["anchor_ref"], inp["topic"],
                           inp.get("motivation", ""),
                           verbose=inp.get("verbose", False))
