"""tools — the SHARED runtime + tool suite for all agents (IPP).

Composed of:
  • the shared core   (tools/graph.py, encoder.py, ipp.py, engine.py,
                       agents.py, build.py, config.py)
  • the ORIGINAL codex 19-tool suite (codex_tools.py)
  • the graph tools (tools/graph_tools.py)
  • the database mutations (database/database_tool)

NOTE: this package init is LAZY (PEP 562). It deliberately does not import
tools.api at module level, so `import tools.config` (needed by database.notes,
database.database_tool, LLMs.deepseek, tools.checks) never triggers the full
api → database.database_tool → database.notes cycle.
"""

from typing import Any


_LAZY_NAMES = ("TOOLS", "TOOL_MAP", "all_definitions", "definitions_for",
               "ensure_tools", "execute_tool")
_LAZY_LOADED = False


def __getattr__(name: str) -> Any:
    global _LAZY_LOADED
    if name in _LAZY_NAMES:
        if not _LAZY_LOADED:
            import tools.api as _api
            _g = globals()
            for _n in _LAZY_NAMES:
                _g[_n] = getattr(_api, _n)
            _LAZY_LOADED = True
        return globals()[name]
    raise AttributeError(f"module 'tools' has no attribute {name!r}")


__all__ = list(_LAZY_NAMES)
