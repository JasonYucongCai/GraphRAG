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


# ── Project-scoped storage (canonical layout, see database/README.md) ─────
# Every generated artifact of a project lives under
#   database/<project>/graph_data/   (knowledge_graph.json · vectors/ ·
#                                     export/ · logs/ · interactive.html)
# The root-level graph_data/ folder does NOT exist anymore.  Which project
# "the current graph" belongs to is decided by database/.active (the last
# opened project); build scripts resolve their own project explicitly.
DB_ROOT = WORKSPACE_ROOT / "database"


def _active_project_slug() -> Optional[str]:
    """Slug of the last-opened project (database/.active), else the first
    project folder that has a project.json, else None."""
    try:
        f = DB_ROOT / ".active"
        if f.exists():
            slug = f.read_text(encoding="utf-8").strip()
            if slug:
                return slug
    except OSError:
        pass
    try:
        for d in sorted(DB_ROOT.iterdir()):
            if d.is_dir() and (d / "project.json").exists():
                return d.name
    except OSError:
        pass
    return None


class _ConfigMeta(type):
    """Metaclass: GRAPH_DIR / GRAPH_JSON / VECTOR_DIR / LOG_DIR resolve at
    READ time against the currently active project — so the same attribute
    follows the project the user opens, with no stale path anywhere."""

    @property
    def DB_DIR(cls) -> Path:
        return cls.db_root()

    @property
    def GRAPH_DIR(cls) -> Path:
        return cls.graph_dir()

    @property
    def GRAPH_JSON(cls) -> Path:
        return cls.graph_json()

    @property
    def VECTOR_DIR(cls) -> Path:
        return cls.vector_dir()

    @property
    def LOG_DIR(cls) -> Path:
        return cls.log_dir()


class Config(metaclass=_ConfigMeta):
    """Central configuration for the graph network + agent runtime.

    Storage paths are PROJECT-SCOPED: ``database/<project>/graph_data/``.
    ``Config.GRAPH_JSON``/``VECTOR_DIR``/``LOG_DIR`` resolve to the currently
    active project (see database/.active) at read time; build scripts that
    target a specific project use ``Config.project_graph_dir(slug)``.
    """

    # ── Workspace ─────────────────────────────────────────────────────────
    WORKSPACE_ROOT: Path = WORKSPACE_ROOT
    ASSETS_DIR: Path = WORKSPACE_ROOT / "assets"

    # ── DeepSeek LLM backend ──────────────────────────────────────────────
    DEEPSEEK_API_KEY: Optional[str] = os.environ.get("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    # DeepSeek V4 family (deepseek-chat/reasoner are deprecated since 2026-07-24)
    DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_THINKING: Optional[str] = os.environ.get("DEEPSEEK_THINKING")  # "medium" | "high"

    # ── Available models (model_id → display label) ────────────────────────
    AVAILABLE_MODELS: dict[str, str] = {
        "deepseek-v4-flash": "DeepSeek V4 Flash",
        "deepseek-v4-pro":   "DeepSeek V4 Pro",
    }

    DEFAULT_MODEL: str = "deepseek-v4-flash"

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

    # ── Project-scoped storage paths ──────────────────────────────────────
    @classmethod
    def db_root(cls) -> Path:
        """database/ — home of every project."""
        return DB_ROOT

    @classmethod
    def active_project_slug(cls) -> Optional[str]:
        """Slug of the currently active project (database/.active)."""
        return _active_project_slug()

    @classmethod
    def project_dir(cls, slug: str) -> Path:
        """database/<slug>/ — one folder per project."""
        return cls.db_root() / slug

    @classmethod
    def project_graph_dir(cls, slug: str) -> Path:
        """database/<slug>/graph_data/ — ALL generated artifacts of a project
        (knowledge_graph.json, vectors/, export/, logs/, interactive.html)."""
        return cls.project_dir(slug) / "graph_data"

    @classmethod
    def graph_dir(cls) -> Path:
        """graph_data/ of the ACTIVE project (fallback: database/default)."""
        return cls.project_graph_dir(cls.active_project_slug() or "default")

    @classmethod
    def graph_json(cls) -> Path:
        """knowledge_graph.json of the ACTIVE project."""
        return cls.graph_dir() / "knowledge_graph.json"

    @classmethod
    def vector_dir(cls) -> Path:
        """vectors/ (encoder index) of the ACTIVE project."""
        return cls.graph_dir() / "vectors"

    @classmethod
    def log_dir(cls) -> Path:
        """logs/ of the ACTIVE project (server + run logs)."""
        return cls.graph_dir() / "logs"

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
        """Create the active project's graph_data/ vectors/ logs/ folders."""
        for d in (cls.graph_dir(), cls.vector_dir(), cls.log_dir()):
            d.mkdir(parents=True, exist_ok=True)
