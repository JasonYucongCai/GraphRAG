"""
tools.build — seed the knowledge graph from the assets folder.

Ingests the three GraphRAG survey papers (assets/pdfs + assets/extracted +
assets/odl_output) into:
  • paper nodes      — one node per paper with metadata
  • concept nodes    — key topics extracted from the surveys
  • typed edges      — papers → concepts, concept → concept (with §4.3a)
  • encoded chunks   — embedded via the EncoderLayer for vector RAG

Output: graph_data/knowledge_graph.json + graph_data/vectors/index.json
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from tools.config import Config
from tools.encoder import EncoderLayer
from tools.graph import KnowledgeGraph

logger = logging.getLogger("tools.build")

# ── Seed corpus metadata (from the workspace assets) ──────────────────────────

PAPERS = [
    {
        "node_id": "peng_survey",
        "entryname": "Graph RAG Survey (Peng et al. 2024)",
        "category": "paper",
        "arxiv": "arXiv:2408.08921v2",
        "description": "First comprehensive survey of GraphRAG: formalizes the "
                       "G-Indexing → G-Retrieval → G-Generation workflow, core "
                       "technologies, training methods, downstream tasks, "
                       "applications, evaluation, and industrial use cases.",
        "pdf": "assets/pdfs/Graph Retrieval-Augmented Generation A Survey 2408.08921v2.pdf",
        "txt": "assets/extracted/Graph Retrieval-Augmented Generation A Survey 2408.08921v2_pypdf.txt",
        "md": "assets/odl_output/Graph Retrieval-Augmented Generation A Survey 2408.08921v2.md",
    },
    {
        "node_id": "han_survey",
        "entryname": "GraphRAG with Graphs (Han et al. 2025)",
        "category": "paper",
        "arxiv": "arXiv:2501.00309v2",
        "description": "Holistic GraphRAG framework with five components (query "
                       "processor, retriever, organizer, generator, data source) "
                       "and a 10-domain taxonomy showing GraphRAG is "
                       "domain-specific, not one-size-fits-all.",
        "pdf": "assets/pdfs/Retrieval-Augmented Generation with Graphs (GraphRAG) 2501.00309v2.pdf",
        "txt": "assets/extracted/Retrieval-Augmented Generation with Graphs (GraphRAG) 2501.00309v2_pypdf.txt",
        "md": "assets/odl_output/Retrieval-Augmented Generation with Graphs (GraphRAG) 2501.00309v2.md",
    },
    {
        "node_id": "yang_survey",
        "entryname": "Graph-based Agent Memory (Yang et al. 2026)",
        "category": "paper",
        "arxiv": "arXiv:2602.05665v1",
        "description": "Survey of graph-based agent memory: taxonomy (short/long-"
                       "term, knowledge/experience, structural/non-structural), "
                       "life cycle (extraction, storage, retrieval, evolution), "
                       "self-evolving memory, applications, and open challenges.",
        "pdf": "assets/pdfs/Graph-based Agent Memory Taxonomy, Techniques, and Applications 2602.05665v1.pdf",
        "txt": "assets/extracted/Graph-based Agent Memory Taxonomy, Techniques, and Applications 2602.05665v1_pypdf.txt",
        "md": "assets/odl_output/Graph-based Agent Memory Taxonomy, Techniques, and Applications 2602.05665v1.md",
    },
]

# ── Concept nodes + edges (seed knowledge, editable/extendable) ───────────────

CONCEPTS = [
    ("grag_framework", "GraphRAG Framework", "concept",
     "5-component architecture: query processor, retriever, organizer, generator, data source."),
    ("g_indexing", "G-Indexing", "concept",
     "Graph-based indexing: construct graph DB + indices (graph/text/vector/hybrid)."),
    ("g_retrieval", "G-Retrieval", "concept",
     "Graph-guided retrieval: nodes/triples/paths/subgraphs at once/iterative/multi-stage granularity."),
    ("g_generation", "G-Generation", "concept",
     "Graph-enhanced generation: GNN/LLM/hybrid generators, graph-to-text formats, training."),
    ("query_processor", "Query Processor", "concept",
     "NER/RE, query structuration (GQL), decomposition, expansion."),
    ("organizer", "Organizer", "concept",
     "Graph pruning, reranking, augmentation, verbalization of retrieved content."),
    ("retriever", "Retriever", "concept",
     "Heuristic/LM/GNN/agent-based retrieval; k-hop, shortest-path, PCST, communities."),
    ("generator", "Generator", "concept",
     "Discrimination/LLM-based/graph-based generation; embedding fusion, LoRA, GIMLET."),
    ("ten_domains", "10-Domain Taxonomy", "concept",
     "KG, document, scientific, social, planning, tabular, infrastructure, biological, scene, random graphs."),
    ("agent_memory", "Agent Memory", "concept",
     "Graph-based memory for LLM agents: extraction, storage, retrieval, evolution."),
    ("memory_extraction", "Memory Extraction", "concept",
     "Transforming observations into memory contents (LLM-extracted nodes/edges)."),
    ("memory_storage", "Memory Storage", "concept",
     "KG, hierarchical DAG, temporal graphs, hypergraphs, hybrid architectures."),
    ("memory_retrieval", "Memory Retrieval", "concept",
     "Six operators: similarity, rule, temporal, graph, RL, agent; + enhancements."),
    ("memory_evolution", "Memory Evolution", "concept",
     "Internal self-evolving (consolidation, graph reasoning, reorganization) + "
     "external self-exploration (feedback adaptation, active inquiry)."),
    ("local_graphs", "Local Graphs (depth-3)", "concept",
     "Depth-k ego networks as bounded working memory for agents; multi-hop reasoning."),
    ("encoder_layer", "Encoder Layer (vector RAG)", "concept",
     "Chunk → embed → vector index → hybrid (similarity ⊕ structure) retrieval."),
    ("hybrid_rag", "Hybrid RAG", "concept",
     "Combining vector similarity retrieval with graph traversal (HybridRAG pattern)."),
    ("community_summary", "Community Summaries", "concept",
     "Leiden communities + LLM summaries for global questions (Microsoft GraphRAG)."),
    ("self_improvement", "Self-Improvement Loop", "concept",
     "External expansion + internal self-evolving + external self-exploration, recursive."),
    ("deepseek_agent", "DeepSeek Agent", "concept",
     "OpenAI-compatible Chat Completions agent powering graph growth and node operations."),
]

# edges: (source, target, relation)
SEED_EDGES = [
    ("peng_survey", "grag_framework", "describes"),
    ("peng_survey", "g_indexing", "describes"),
    ("peng_survey", "g_retrieval", "describes"),
    ("peng_survey", "g_generation", "describes"),
    ("han_survey", "grag_framework", "describes"),
    ("han_survey", "ten_domains", "describes"),
    ("han_survey", "retriever", "describes"),
    ("han_survey", "organizer", "describes"),
    ("han_survey", "generator", "describes"),
    ("han_survey", "query_processor", "describes"),
    ("yang_survey", "agent_memory", "describes"),
    ("yang_survey", "memory_extraction", "describes"),
    ("yang_survey", "memory_storage", "describes"),
    ("yang_survey", "memory_retrieval", "describes"),
    ("yang_survey", "memory_evolution", "describes"),
    # concept-level structure
    ("grag_framework", "query_processor", "contains"),
    ("grag_framework", "retriever", "contains"),
    ("grag_framework", "organizer", "contains"),
    ("grag_framework", "generator", "contains"),
    ("g_indexing", "encoder_layer", "uses"),
    ("g_retrieval", "local_graphs", "uses"),
    ("g_retrieval", "hybrid_rag", "uses"),
    ("g_retrieval", "community_summary", "uses"),
    ("g_generation", "community_summary", "uses"),
    ("agent_memory", "memory_evolution", "extends"),
    ("agent_memory", "local_graphs", "uses"),
    ("memory_evolution", "self_improvement", "implements"),
    ("self_improvement", "deepseek_agent", "driven_by"),
    ("deepseek_agent", "encoder_layer", "uses"),
    ("encoder_layer", "hybrid_rag", "enables"),
    ("local_graphs", "self_improvement", "enables"),
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")


def build_graph(
    graph: Optional[KnowledgeGraph] = None,
    encoder: Optional[EncoderLayer] = None,
    ingest_chunks: bool = True,
    assets_root: Optional[Path] = None,
) -> tuple[KnowledgeGraph, EncoderLayer]:
    """Seed the knowledge graph from assets. Returns (graph, encoder)."""
    root = Path(assets_root or Config.WORKSPACE_ROOT)
    graph = graph or KnowledgeGraph()
    encoder = encoder or EncoderLayer()

    # 1. Paper nodes (idempotent: skip if already present)
    for p in PAPERS:
        if graph.get_node(p["node_id"]) is None:
            graph.add_node(
                p["node_id"], p["entryname"], category="paper",
                description=p["description"],
                content={"arxiv": p["arxiv"], "pdf": p["pdf"],
                         "txt": p["txt"], "md": p["md"]},
            )

    # 2. Concept nodes
    for nid, name, cat, desc in CONCEPTS:
        if graph.get_node(nid) is None:
            graph.add_node(nid, name, category=cat, description=desc)

    # 3. Edges
    for source, target, rel in SEED_EDGES:
        try:
            if not graph.has_edge(source, target, rel):
                graph.add_edge(source, target, relation=rel)
        except ValueError as exc:
            logger.warning("seed edge skipped: %s", exc)

    # 4. Encode paper chunks (text index + vector index)
    if ingest_chunks:
        for p in PAPERS:
            txt_path = root / p["txt"]
            if txt_path.exists():
                text = txt_path.read_text(encoding="utf-8", errors="replace")
                # section-aware: split on --- PAGE n --- markers
                sections = re.split(r"--- PAGE \d+ ---", text)
                for i, sec in enumerate(sections, 1):
                    sec = sec.strip()
                    if len(sec) < 40:
                        continue
                    encoder.ingest(p["node_id"], sec,
                                   section=f"page-{i}",
                                   source_ref={"file": p["txt"], "page": i})
            else:
                logger.warning("missing extracted text: %s", txt_path)
        # node meta summaries for node-level search
        for nid, node in graph._nodes.items():
            encoder.ingest_meta(nid, f"{node.entryname} {node.description}")

    # 5. Persist
    graph.pagerank()
    Config.ensure_dirs()
    graph.save()
    encoder.save()
    return graph, encoder


def export_backward_compatible(graph: KnowledgeGraph, out_root: Optional[Path] = None) -> Path:
    """
    Emit the ScientificInfrastructure-compatible registry + per-node
    input.json/output.json into graph_data/export/.
    """
    out = Path(out_root or (Config.GRAPH_DIR / "export"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "structurelist.json").write_text(
        json.dumps(graph.to_structurelist(), ensure_ascii=False, indent=1),
        encoding="utf-8")
    for nid, files in graph.to_edges_files().items():
        folder = out / str(nid)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "input.json").write_text(
            json.dumps(files["input.json"], ensure_ascii=False, indent=1),
            encoding="utf-8")
        (folder / "output.json").write_text(
            json.dumps(files["output.json"], ensure_ascii=False, indent=1),
            encoding="utf-8")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    g, enc = build_graph()
    print(g.summary())
    print(f"chunks indexed: {enc.index.size()}")
    export_backward_compatible(g)
    print(f"exported: {Config.GRAPH_DIR / 'export'}")
