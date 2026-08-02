"""
tools.config — self-contained configuration for the Graph Knowledge Network.

Loads credentials from the workspace's LLMs/.env (DeepSeek keys, models, base URL)
so the graph agents can talk to DeepSeek's OpenAI-compatible Chat Completions API.
Never hard-code secrets here; always read from environment / .env.

This is the merged Config: the original graph_network Config PLUS the codex
tool-suite extras (PUSHOVER_USER/TOKEN, get_conda_activate_prefix) so both the
graph tools and the ported codex suite read one configuration.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# ── Package location ──────────────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = Path(os.environ.get("GRAPH_WORKSPACE", PACKAGE_DIR.parent))

# The DeepSeek credential file lives in the top-level LLMs/ folder (moved from
# codex/LLMs/ during the 2026-08-02 multi-agent restructure).
_ENV_CANDIDATES = [
    Path(p) for p in (
        os.environ.get("GRAPH_ENV_FILE", ""),
        WORKSPACE_ROOT / "LLMs" / ".env",                    # canonical location
        WORKSPACE_ROOT / "codex" / "LLMs" / ".env",          # legacy location
        WORKSPACE_ROOT / "assets" / "codex" / "LLMs" / ".env",  # older legacy
    ) if str(p)
]
ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _ENV_CANDIDATES[0])


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader: KEY=VALUE lines, # comments, no dependencies."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ENV_FILE)


class Config:
    """Central configuration for the graph network + agent runtime."""

    # ── Workspace ─────────────────────────────────────────────────────────
    WORKSPACE_ROOT: Path = WORKSPACE_ROOT
    ASSETS_DIR: Path = WORKSPACE_ROOT / "assets"
    GRAPH_DIR: Path = WORKSPACE_ROOT / "graph_data"
    GRAPH_JSON: Path = GRAPH_DIR / "knowledge_graph.json"
    VECTOR_DIR: Path = GRAPH_DIR / "vectors"
    LOG_DIR: Path = GRAPH_DIR / "logs"

    # ── DeepSeek LLM backend ──────────────────────────────────────────────
    DEEPSEEK_API_KEY: Optional[str] = os.environ.get("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    # DeepSeek V4 family (deepseek-chat/reasoner are deprecated since 2026-07-24)
    DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_THINKING: Optional[str] = os.environ.get("DEEPSEEK_THINKING")  # "medium" | "high"

    # ── Agent runtime ─────────────────────────────────────────────────────
    MAX_TOOL_ROUNDS: int = int(os.environ.get("GRAPH_MAX_TOOL_ROUNDS", "15"))
    MAX_CONTEXT: int = 1_000_000          # DeepSeek V4: 1M token context
    COMPACT_THRESHOLD: int = 200_000      # compact when fewer chars*4 remain
    TRUNCATE_OLD_TOOL_CHARS: int = 300
    TEMPERATURE: float = 0.3
    MAX_TOKENS: int = 4096

    # ── Graph growth guardrails (ScientificInfrastructure §4.5a / §4.7c) ──
    MAX_NEW_SUBJECTS_PER_RUN: int = 5
    MAX_REFS_PER_SUBJECT_PER_RUN: int = 5
    MAX_REFS_PER_RUN: int = 50
    LOCAL_DEPTH: int = 3                    # default local-graph depth

    # ── Encoder layer ─────────────────────────────────────────────────────
    EMBED_DIM: int = 384
    CHUNK_CHARS: int = 1200
    CHUNK_OVERLAP: int = 200
    VECTOR_TOP_K: int = 20
    HYBRID_ALPHA: float = 0.6               # similarity vs structure weight

    # ── codex tool-suite extras (merged from the original tools/config shim)
    PUSHOVER_USER: str = os.environ.get("PUSHOVER_USER", "")
    PUSHOVER_TOKEN: str = os.environ.get("PUSHOVER_TOKEN", "")

    @staticmethod
    def get_conda_activate_prefix() -> str:
        """Conda env prefix injected before shell commands (best-effort)."""
        env = os.environ.get("CONDA_DEFAULT_ENV", "")
        prefix = os.environ.get("CONDA_PREFIX", "")
        if env and prefix:
            return f"conda run -n {env} "
        return ""

    # ── LLM accessors ─────────────────────────────────────────────────────
    @classmethod
    def api_key(cls) -> str:
        key = cls.DEEPSEEK_API_KEY or os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY not found. Add it to LLMs/.env or set the "
                "environment variable before running graph agents."
            )
        return key

    @classmethod
    def get_model(cls) -> str:
        return cls.DEEPSEEK_MODEL

    @classmethod
    def ensure_dirs(cls) -> None:
        for d in (cls.GRAPH_DIR, cls.VECTOR_DIR, cls.LOG_DIR):
            d.mkdir(parents=True, exist_ok=True)
