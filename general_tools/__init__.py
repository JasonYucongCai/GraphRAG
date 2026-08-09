"""general_tools — the SHARED runtime + tool suite for all agents (IPP).

The shared runtime is the **tools** IPP node (general_tools/IPP.json via
Γ — 26 channels: invoke/list/describe router + graph/encoder/build/check
+ the 19 codex channels). The tool definitions the LLM sees are derived
from the F-file channel schemas (general_tools/catalog.py); the router
lives in general_tools/routes.py; the domain operations in
general_tools/impl.py.

There is NO api layer: callers use the node directly —

    from general_tools.construct import tools_node
    out = tools_node().invoke("invoke", {"tool": "read_file", "args": {...}})

NOTE: this package init is LAZY (PEP 562) — it does not import the heavy
modules at package-import time, so `import general_tools.config` (needed
by database.notes, LLMs.deepseek) never triggers a heavy import chain.
"""
from typing import Any

_LAZY_NAMES = ("tools_node", "bind_tools")
_LAZY_LOADED = False


def __getattr__(name: str) -> Any:
    global _LAZY_LOADED
    if name in _LAZY_NAMES:
        if not _LAZY_LOADED:
            from general_tools import construct as _c
            _g = globals()
            for _n in _LAZY_NAMES:
                _g[_n] = getattr(_c, _n)
            _LAZY_LOADED = True
        return globals()[name]
    raise AttributeError(f"module 'general_tools' has no attribute {name!r}")


__all__ = list(_LAZY_NAMES)
