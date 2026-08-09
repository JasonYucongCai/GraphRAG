"""
tools.build_multiagent — seed the **Multi-Agent Network** knowledge graph + note database.

Sources: 21 arXiv papers spanning the multi-agent stack:

  LLM multi-agent frameworks    AutoGen · MetaGPT · ChatDev · CAMEL · AgentVerse ·
                                AutoAgents · Agents (open-source framework)
  collaboration mechanisms      Multi-agent collaboration survey · social-psychology
                                view · Solo Performance Prompting · Multiagent Debate ·
                                DyLAN (dynamic agent teams)
  surveys                       LLM-based MAS survey · Rise & Potential · Autonomous
                                Agents survey
  memory & society              Generative Agents
  evaluation                    AgentBench
  MARL foundations              MARL survey · Learning to Communicate (DIAL) · SMAC
  graph reasoning               Graph of Thoughts

Pipeline (project-scoped — see database/README.md):
  1. arXiv API  → metadata (title/authors/abstract/categories)
  2. download   → database/multi-agent-network/assets/papers/*.pdf
  3. pypdf      → database/multi-agent-network/assets/extracted/*.txt
  4. graph      → database/multi-agent-network/graph_data/knowledge_graph.json
                  (paper nodes + concept nodes + typed edges, auto_load=True)
  5. notes      → database/multi-agent-network/nodes/*.md (one living note per node,
                  curated deep-dive content, [[wikilinks]] = edges, VCL)
  6. assets     → assets/manifest.json + assets/README.md (node ↔ file)
  7. export     → database/multi-agent-network/graph_data/interactive.html (PyVis-style)

Run from the workspace root:
    python -m tools.build_multiagent            # full pipeline (resumable)
    python -m tools.build_multiagent --no-download   # reuse existing PDFs only
    python -m tools.build_multiagent --no-extract    # reuse existing extractions
    python -m tools.build_multiagent --force-download  # re-download all PDFs

The web control center can serve the graph with:
    python ui/server.py --graph database/multi-agent-network/graph_data
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from general_tools.config import Config
from general_tools.graph import KnowledgeGraph, RELATION_VOCAB
from general_tools.build_cy3 import sync_project_assets
from general_tools.multiagent_corpus import PAPERS, CONCEPTS, EDGES
from ui.visuals import interactive_html
from database.notes import NoteStore

logger = logging.getLogger("general_tools.build_multiagent")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# ── Folders ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Config.WORKSPACE_ROOT / "database" / "multi-agent-network"
PAPERS_DIR = PROJECT_DIR / "assets" / "papers"
EXTRACTED_DIR = PROJECT_DIR / "assets" / "extracted"
OUT_DIR = Config.project_graph_dir("multi-agent-network")
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_PDF = "https://arxiv.org/pdf/{aid}"
UA = {"User-Agent": "GraphKG-build/1.0 (research; contact: local)"}

# Domain relations (advisory extension — matches the build_cy3 pattern)
RELATION_VOCAB |= {"introduces", "surveys", "exemplifies", "founds", "addresses"}

PROJECT_TITLE = "Multi-Agent Network"
PROJECT_DESC = (
    "Multi-agent systems for LLM agents and beyond: frameworks (AutoGen, MetaGPT, "
    "ChatDev, CAMEL, AgentVerse), collaboration mechanisms (debate, role-play, social "
    "psychology), MARL foundations (MARL survey, DIAL, SMAC), memory (Generative "
    "Agents), evaluation (AgentBench) — 21 arXiv papers with deep-dive analysis, "
    "28 concepts, ~201 typed edges."
)

# ══════════════════════════════════════════════════════════════════════════════
# arXiv metadata — fetch once, cache next to the project
# ══════════════════════════════════════════════════════════════════════════════

ARXIV_CACHE = PROJECT_DIR / "arxiv_meta.json"


def fetch_arxiv_metadata(aids: list[str], force: bool = False) -> dict[str, dict]:
    """Fetch title/authors/abstract/categories for the given arXiv ids (cached)."""
    if ARXIV_CACHE.exists() and not force:
        try:
            cached = json.loads(ARXIV_CACHE.read_text(encoding="utf-8"))
            if all(a in cached for a in aids):
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    out: dict[str, dict] = {}
    # arXiv API allows batches; query in chunks to stay polite
    for i in range(0, len(aids), 10):
        chunk = aids[i:i + 10]
        url = f"{ARXIV_API}?id_list={urllib.parse.quote(','.join(chunk))}"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            xml = r.read().decode("utf-8", "replace")
        entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
        for e in entries:
            aid = re.search(r"<id>http://arxiv.org/abs/([^v<]+)", e)
            if not aid:
                continue
            aid = aid.group(1)
            title = re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1)).strip()
            summary = re.sub(r"\s+", " ", re.search(r"<summary>(.*?)</summary>", e, re.S).group(1)).strip()
            authors = re.findall(r"<name>(.*?)</name>", e)
            cats = re.findall(r'term="([^"]+)"', e)
            published = re.search(r"<published>(\d{4})", e)
            out[aid] = {
                "arxiv_id": aid, "title": title, "abstract": summary,
                "authors": authors, "categories": cats[:8],
                "year": published.group(1) if published else "",
            }
        time.sleep(1)
    ARXIV_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ARXIV_CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Download + extraction
# ══════════════════════════════════════════════════════════════════════════════

def _slugify(text: str, words: int = 4) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_").strip("_")
    parts = [p for p in slug.split("_") if p]
    return "_".join(parts[:words]) or "paper"


def pdf_stem(meta: dict) -> str:
    """Descriptive filename: {FirstAuthor}_{Year}_{TitleSlug}_{arxiv_id}
    (e.g. Wu_2023_autogen_enabling_next_gen_2308.08155). The arXiv id is part
    of the name so papers are unambiguous across versions."""
    author = re.sub(r"[^A-Za-z]", "", meta["authors"][0].split()[-1]) if meta.get("authors") else "anon"
    return f"{author}_{meta.get('year', '')}_{_slugify(meta['title'], 4)}_{meta.get('arxiv_id', '')}"


def _has_curl() -> bool:
    """Windows ships curl.exe; macOS/Linux usually too."""
    try:
        import shutil as _sh
        return _sh.which("curl") is not None
    except Exception:  # noqa: BLE001
        return False


CURL_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _download_one_curl(url: str, dst: Path) -> int:
    """Download with curl.exe — robust redirects + retries. Returns bytes written."""
    cmd = [
        "curl", "-sS", "-L", "--fail", "--retry", "5", "--retry-delay", "3",
        "--retry-all-errors", "--max-time", "300", "--connect-timeout", "20",
        "-A", CURL_UA, "-o", str(dst), url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise IOError(f"curl exit {proc.returncode}: {proc.stderr.strip()[-300:]}")
    return dst.stat().st_size


def _download_one_urllib(url: str, dst: Path) -> int:
    """Fallback downloader (no curl available)."""
    req = urllib.request.Request(url, headers={"User-Agent": CURL_UA})
    with urllib.request.urlopen(req, timeout=120) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f)
    return dst.stat().st_size


def download_pdfs(meta_map: dict[str, dict], force: bool = False,
                  no_download: bool = False) -> dict[str, Path]:
    """Download every paper PDF into assets/papers/ (resumable).

    Skips files already present (>= 20 KB) unless ``force``. Progress is
    printed per file (i/N) with the size after each download. arXiv is
    rate-limited politely (3 s between requests). Returns nid → pdf path.
    """
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    use_curl = _has_curl()
    if use_curl:
        logger.info("downloader: curl.exe (redirects + retries enabled)")
    else:
        logger.warning("curl not found — falling back to urllib")
    result: dict[str, Path] = {}
    total = len(PAPERS)
    for idx, entry in enumerate(PAPERS, 1):
        meta = meta_map[entry["aid"]]
        stem = pdf_stem(meta)
        pdf_path = PAPERS_DIR / f"{stem}.pdf"
        if pdf_path.exists() and pdf_path.stat().st_size >= 20_000:
            if no_download or not force:
                logger.info("[%d/%d] %-14s already present (%d KB) — reusing",
                            idx, total, entry["nid"], pdf_path.stat().st_size // 1024)
                result[entry["nid"]] = pdf_path
                continue
        if no_download:
            logger.warning("[%d/%d] %-14s missing and --no-download: skipped",
                           idx, total, entry["nid"])
            continue
        url = ARXIV_PDF.format(aid=entry["aid"])
        ok = False
        for attempt in range(3):
            try:
                logger.info("[%d/%d] %-14s downloading arXiv:%s …", idx, total,
                            entry["nid"], entry["aid"])
                size = (_download_one_curl(url, pdf_path) if use_curl
                        else _download_one_urllib(url, pdf_path))
                if size < 20_000:
                    raise IOError(f"suspiciously small PDF ({size} B)")
                logger.info("[%d/%d] %-14s downloaded  %d KB", idx, total,
                            entry["nid"], size // 1024)
                result[entry["nid"]] = pdf_path
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%d/%d] %-14s attempt %d failed: %s",
                               idx, total, entry["nid"], attempt + 1, str(exc)[:200])
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        if not ok:
            raise RuntimeError(f"could not download {entry['aid']} ({entry['nid']})")
        if idx < total:
            time.sleep(3)  # arXiv etiquette: ≥3 s between requests
    return result


def extract_texts(pdf_map: dict[str, Path], skip: bool = False) -> dict[str, Path]:
    """pypdf extraction of every PDF into assets/extracted/. Returns nid → txt path."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        logger.warning("pypdf not available (%s) — skipping extraction", exc)
        return {}
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for entry in PAPERS:
        pdf_path = pdf_map.get(entry["nid"])
        if pdf_path is None or not pdf_path.exists():
            logger.warning("extraction skipped for %s: PDF missing", entry["nid"])
            continue
        txt_path = EXTRACTED_DIR / f"{pdf_path.stem}.txt"
        if skip and txt_path.exists():
            result[entry["nid"]] = txt_path
            continue
        try:
            reader = PdfReader(str(pdf_path))
            pages = []
            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                except Exception:  # noqa: BLE001
                    text = ""
                pages.append(f"\n--- page {i + 1} ---\n{text.strip()}")
            txt_path.write_text("\n".join(pages), encoding="utf-8")
            logger.info("extracted %s → %d chars / %d pages",
                        entry["nid"], txt_path.stat().st_size, len(reader.pages))
            result[entry["nid"]] = txt_path
        except Exception as exc:  # noqa: BLE001
            logger.warning("extraction failed for %s: %s", entry["nid"], exc)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Graph + notes
# ══════════════════════════════════════════════════════════════════════════════

def paper_content_md(entry: dict, meta: dict, pdf: Optional[Path], txt: Optional[Path]) -> str:
    """The deep-dive markdown body for one paper note."""
    md = [
        "### arXiv",
        f"- **ID:** arXiv:{entry['aid']}",
        f"- **Title:** {meta['title']}",
        f"- **Authors:** {', '.join(meta['authors'][:12])}"
        + (" et al." if len(meta["authors"]) > 12 else ""),
        f"- **Year:** {meta.get('year', '')}",
        f"- **Categories:** {', '.join(meta.get('categories', [])[:6])}",
        "",
        "### Abstract",
        meta["abstract"],
        "",
        "### Contribution",
        entry["contribution"],
        "",
        "### Method",
        entry["method"],
        "",
        "### Key Results",
        entry["key_results"],
        "",
        "### Findings",
        entry["findings"],
        "",
        "### Significance",
        entry["significance"],
    ]
    if pdf and txt:
        md += [
            "",
            "### Assets",
            f"- PDF: `assets/papers/{pdf.name}` ({pdf.stat().st_size // 1024} KB)",
            f"- Text: `assets/extracted/{txt.name}` ({txt.stat().st_size // 1024} KB)",
        ]
    return "\n".join(md)


def concept_content_md(entry: dict) -> str:
    return (
        f"### What it is\n{entry['desc']}\n\n"
        "### Why it matters\n"
        "Concepts are the *network layer* of this knowledge base: papers attach to "
        "concepts through typed edges, so a query can move from a framework to the "
        "mechanism it uses to the papers that study that mechanism.\n\n"
        "### Key papers\n"
        "See the Links section — every `[[wikilink]]` pointing here is a paper "
        "that defines, uses, surveys or enables this concept."
    )


def build(no_download: bool = False, no_extract: bool = False,
          force_download: bool = False) -> dict:
    """Run the full pipeline. Returns a summary dict."""
    started = time.time()
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_DIR / "nodes").mkdir(exist_ok=True)
    (PROJECT_DIR / "assets").mkdir(exist_ok=True)

    # 1. metadata
    aids = [p["aid"] for p in PAPERS]
    meta_map = fetch_arxiv_metadata(aids)
    missing = [a for a in aids if a not in meta_map]
    if missing:
        raise RuntimeError(f"arXiv metadata missing for: {missing}")

    # 2. download + 3. extraction
    pdf_map = download_pdfs(meta_map, force=force_download, no_download=no_download)
    txt_map = extract_texts(pdf_map, skip=no_extract)

    # 4. graph
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    graph = KnowledgeGraph(path=OUT_DIR / "knowledge_graph.json", auto_load=True)

    added_nodes = added_edges = 0
    for entry in PAPERS:
        meta = meta_map[entry["aid"]]
        nid = entry["nid"]
        content = {"arxiv": entry["aid"]}
        if nid in pdf_map:
            content["pdf"] = str(pdf_map[nid])
        if nid in txt_map:
            content["txt"] = str(txt_map[nid])
        if graph.get_node(nid) is None:
            graph.add_node(nid, meta["title"], category="paper",
                           description=entry["takeaway"], content=content)
            added_nodes += 1
        else:
            # keep the node's content fresh on rebuilds (paths may have moved)
            graph.update_node(nid, entryname=meta["title"],
                              description=entry["takeaway"], content=content)
    for c in CONCEPTS:
        if graph.get_node(c["nid"]) is None:
            graph.add_node(c["nid"], c["name"], category="concept",
                           description=c["desc"])
            added_nodes += 1
    for src, dst, rel in EDGES:
        if not graph.has_edge(src, dst, rel):
            graph.add_edge(src, dst, relation=rel, agent_run="seed-multiagent")
            added_edges += 1
    graph.pagerank()
    graph.save()

    # 5. note database project (idempotent; preserves existing VCL/content)
    store = NoteStore()
    if store.current() != "multi-agent-network":
        try:
            store.open_project("multi-agent-network")
        except ValueError:
            raise RuntimeError("database/multi-agent-network/project.json missing")
    res = store.sync_from_graph(graph)
    enriched = 0
    for entry in PAPERS:
        meta = meta_map[entry["aid"]]
        note = store.get_note(entry["nid"])
        note.content = paper_content_md(
            entry, meta, pdf_map.get(entry["nid"]), txt_map.get(entry["nid"]))
        note.tags = sorted(set((note.tags or []) + entry["tags"]))
        store.save_note(note, author="build-multiagent",
                        summary="Added arXiv metadata + curated deep-dive analysis.")
        enriched += 1
    for c in CONCEPTS:
        note = store.get_note(c["nid"])
        note.content = concept_content_md(c)
        note.tags = sorted(set((note.tags or []) + ["concept"]))
        store.save_note(note, author="build-multiagent",
                        summary="Added concept definition and network-layer note.")
        enriched += 1

    # 6. assets manifest (copies files + writes manifest.json / README.md)
    manifest = sync_project_assets(graph, PROJECT_DIR)

    # 7. interactive export
    (OUT_DIR / "interactive.html").write_text(
        interactive_html(graph, title="Multi-Agent Network — Knowledge Graph"),
        encoding="utf-8")

    elapsed = time.time() - started
    return {
        "elapsed_s": round(elapsed, 1),
        "nodes": len(graph._nodes),
        "edges": len(graph._edges),
        "added_nodes": added_nodes,
        "added_edges": added_edges,
        "papers": len(PAPERS),
        "pdfs": len(pdf_map),
        "texts": len(txt_map),
        "notes_sync": res,
        "notes_enriched": enriched,
        "manifest_nodes": len(manifest),
        "graph_path": str(graph.path),
        "project_dir": str(PROJECT_DIR),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = sys.argv[1:]
    summary = build(no_download="--no-download" in args,
                    no_extract="--no-extract" in args,
                    force_download="--force-download" in args)
    print("\n" + "═" * 72)
    print("Multi-Agent Network build complete")
    print("═" * 72)
    for k, v in summary.items():
        print(f"  {k:18s} {v}")
    print("═" * 72)
    print(f"serve with: python ui/server.py --graph {OUT_DIR}")


if __name__ == "__main__":
    main()
