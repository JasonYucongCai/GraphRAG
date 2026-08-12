"""
tools.encoder — the Encoder Layer (vector-based RAG extraction).

Requirement: "encoder-like capability for a vector-based RAG extraction to
the nodes". This module implements:

  • Chunking     — section-aware splitting of node content into chunks
  • Embedding    — pluggable: hash-bag fallback (offline) or any embed model
                   exposing embed_text(); the interface is the capability
  • Vector index — numpy cosine similarity over per-chunk vectors
  • Hybrid score — similarity ⊕ structure (PageRank / hop bonus), §6.6

The encoder is an IPP: (text chunk) → Φ → vector, and (query, k) → Φ → hits.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from general_tools.config import Config

logger = logging.getLogger("general_tools.encoder")


# ══════════════════════════════════════════════════════════════════════════════
# Embedding interface — the "encoder-like capability"
# ══════════════════════════════════════════════════════════════════════════════


class Embedder:
    """Pluggable embedding interface. Subclass or duck-type for real models."""

    dim: int = Config.EMBED_DIM

    def embed_text(self, text: str) -> list[float]:
        """Embed a batch of text strings → list of numpy vectors.
        Uses the sentence-transformers model for efficient batch encoding."""

        """Embed a single text string → numpy vector using the configured
        embedding model (default: sentence-transformers/all-MiniLM-L6-v2).
        Returns a list[float] of dimension 384.
        This is the TOP-LEVEL helper; the EncoderLayer delegates to it."""

        raise NotImplementedError

    def embed(self, text: str) -> list[float]:
        return self.embed_text(text)


class HashEmbedder(Embedder):
    """
    Deterministic offline embedder: feature-hashing of character 4-grams into
    a fixed-dim vector + TF weighting. No network, no model — good enough for
    building the graph and testing the pipeline; swap for bge-m3 etc. anytime.
    """

    dim = Config.EMBED_DIM

    def __init__(self, dim: int = Config.EMBED_DIM):
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        toks = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        for tok in toks:
            grams = [tok[i:i + 4] for i in range(max(1, len(tok) - 3))] or [tok]
            for g in grams:
                h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
                vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()


# ══════════════════════════════════════════════════════════════════════════════
# Chunks & Vector Index
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class Chunk:
    chunk_id: str
    node_id: Any
    section: str
    text: str
    source_ref: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "node_id": self.node_id,
            "section": self.section,
            "text": self.text,
            "source_ref": self.source_ref,
        }


@dataclass
class VectorIndex:
    """numpy cosine-similarity index over chunk embeddings."""

    chunks: list[Chunk] = field(default_factory=list)
    vectors: list[np.ndarray] = field(default_factory=list)

    def add(self, chunk: Chunk, vector: list[float]) -> None:
        self.chunks.append(chunk)
        self.vectors.append(np.asarray(vector, dtype=np.float32))

    def search(self, query_vec: list[float], k: int = 10,
               node_filter: Optional[Any] = None) -> list[tuple[Chunk, float]]:
        """Top-k chunks by cosine similarity."""
        if not self.vectors:
            return []
        q = np.asarray(query_vec, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        q = q / qn
        scores = []
        for i, v in enumerate(self.vectors):
            chunk = self.chunks[i]
            if node_filter is not None and chunk.node_id != node_filter:
                continue
            vn = np.linalg.norm(v)
            sim = float(np.dot(q, v) / vn) if vn > 0 else 0.0
            scores.append((chunk, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]

    def size(self) -> int:
        return len(self.chunks)

    def save(self, path: Path) -> None:
        payload = {
            "chunks": [c.to_dict() for c in self.chunks],
            "vectors": [v.tolist() for v in self.vectors],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def load(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.chunks = [Chunk(**{k: v for k, v in c.items() if k in Chunk.__dataclass_fields__})
                       for c in payload["chunks"]]
        self.vectors = [np.asarray(v, dtype=np.float32) for v in payload["vectors"]]


# ══════════════════════════════════════════════════════════════════════════════
# EncoderLayer — orchestrates chunk → embed → index → hybrid search
# ══════════════════════════════════════════════════════════════════════════════


class EncoderLayer:
    """
    The encoder-like capability of the network:

      • ingest(node_id, text, section, source_ref)  → chunk embedded + indexed
      • search(query, k, node_filter)               → top-k chunks + scores
      • hybrid(query, k, graph, anchor)             → structure-aware rerank
    """

    name = "encoder"

    def __init__(self, embedder: Optional[Embedder] = None,
                 chunk_chars: int = Config.CHUNK_CHARS,
                 overlap: int = Config.CHUNK_OVERLAP):
        self.embedder = embedder or HashEmbedder()
        self.chunk_chars = chunk_chars
        self.overlap = overlap
        self.index = VectorIndex()
        self._chunk_seq = 0

    # ── chunking ──────────────────────────────────────────────────────────
    def chunk_text(self, text: str, section: str = "") -> list[str]:
        """Split long text into overlapping character chunks at word boundaries."""
        text = text.strip()
        if len(text) <= self.chunk_chars:
            return [text] if text else []
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_chars, len(text))
            if end < len(text):
                # back off to the last space or newline
                cut = max(text.rfind(" ", start + self.chunk_chars // 2, end),
                          text.rfind("\n", start + self.chunk_chars // 2, end))
                if cut > start + self.chunk_chars // 2:
                    end = cut
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= len(text):
                break
            start = max(end - self.overlap, start + 1)
        return chunks

    # ── ingestion ─────────────────────────────────────────────────────────
    def ingest(self, node_id: Any, text: str, section: str = "",
               source_ref: Optional[dict] = None) -> int:
        """Chunk, embed, and index `text` under `node_id`. Returns # chunks."""
        n = 0
        for piece in self.chunk_text(text, section):
            self._chunk_seq += 1
            chunk = Chunk(
                chunk_id=f"vec://{node_id}/c{self._chunk_seq:04d}",
                node_id=node_id,
                section=section or "general",
                text=piece,
                source_ref=source_ref,
            )
            self.index.add(chunk, self.embedder.embed(piece))
            n += 1
        return n

    def ingest_meta(self, node_id: Any, summary: str) -> None:
        """Index a node-level summary embedding for node similarity search."""
        chunk = Chunk(chunk_id=f"vec://{node_id}/meta", node_id=node_id,
                      section="__meta__", text=summary)
        self.index.add(chunk, self.embedder.embed(summary))

    # ── search ────────────────────────────────────────────────────────────
    def search(self, query: str, k: int = Config.VECTOR_TOP_K,
               node_filter: Optional[Any] = None) -> list[tuple[Chunk, float]]:
        return self.index.search(self.embedder.embed(query), k=k, node_filter=node_filter)

    def search_nodes(self, query: str, k: int = 10) -> list[tuple[Any, float]]:
        """Rank nodes by similarity of their meta summaries."""
        qv = self.embedder.embed(query)
        best: dict[Any, float] = {}
        for chunk, sim in self.index.search(qv, k=len(self.index.chunks)):
            if chunk.section == "__meta__":
                best[chunk.node_id] = max(best.get(chunk.node_id, 0.0), sim)
        ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)[:k]
        return ranked

    def hybrid_search(self, query: str, graph, anchor: Any,
                      k: int = Config.VECTOR_TOP_K,
                      alpha: float = Config.HYBRID_ALPHA) -> list[tuple[Any, float]]:
        """
        Hybrid scoring over the local graph of `anchor`:
            score(node) = α·sim(q, node) + (1−α)·pagerank(node) + hop_bonus
        Returns ranked node_ids that exist inside L_k(anchor).
        """
        local = graph.materialize_local(anchor, depth=Config.LOCAL_DEPTH)
        pr = graph.pagerank()
        scores: dict[Any, float] = {}
        for chunk, sim in self.search(query, k=len(self.index.chunks)):
            nid = chunk.node_id
            if nid not in local.nodes:
                continue
            base = scores.get(nid, 0.0)
            scores[nid] = base + alpha * sim
        for nid in local.nodes:
            scores[nid] = scores.get(nid, 0.0) + (1 - alpha) * pr.get(nid, 0.0)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:k]

    # ── persistence ───────────────────────────────────────────────────────
    def save(self, path: Optional[Path] = None) -> Path:
        target = path or (Config.VECTOR_DIR / "index.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        self.index.save(target)
        return target

    def load(self, path: Optional[Path] = None) -> None:
        target = path or (Config.VECTOR_DIR / "index.json")
        if target.exists():
            self.index.load(target)
            self._chunk_seq = len(self.index.chunks)
