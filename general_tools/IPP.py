"""
tools.IPP — legacy IPP abstraction (deprecated, kept for backward compatibility).

The old ``IPP`` base class (I, Φ, O) and ``ToolResult`` remain here.  The
canonical agent types ``ToolCallEvent`` and ``ToolContext`` now live in
``graph_agent.types`` — they are RE-EXPORTED below so existing imports
don't break.

New code MUST import from the canonical locations:

    from graph_agent import AgentEngine, ToolCallEvent, ToolContext
    from IPP import IPPFile, IPPConstructor, IPPNode, IPPObject, IPPExecutor
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar

# ── canonical re-exports (backward compatibility) ─────────────────────────
from graph_agent.types import ToolCallEvent, ToolContext  # noqa: F401

logger = logging.getLogger("general_tools.IPP")

I = TypeVar("I")
O = TypeVar("O")

# ══════════════════════════════════════════════════════════════════════════════
# IPP — the universal information-processing abstraction
# ══════════════════════════════════════════════════════════════════════════════


class IPP(Generic[I, O]):
    """
    Information Processing Protocol: the minimal complete abstraction.

    IPP = (Input, Φ, Output) with Φ: Input → Output.

    Properties:
      • composable:  IPP(B) ∘ IPP(A) is an IPP
      • observable:  every invocation records (input, elapsed, output, error)
      • swappable:   any concrete implementation of the same contract fits
    """

    name: str = "IPP"

    def __init__(self, phi: Optional[Callable[[I], O]] = None):
        self._phi = phi or self.transform
        self._observations: list[dict] = []

    # Override in subclass when not using the constructor callable.
    def transform(self, inp: I) -> O:
        raise NotImplementedError(f"{self.name}.transform()")

    def run(self, inp: I, **ctx) -> O:
        """Execute this IPP: record an observation, delegate to Φ."""
        t0 = time.perf_counter()
        error = None
        try:
            out = self._phi(inp)
        except Exception as exc:  # noqa: BLE001 — observations must never crash the caller
            error = f"{type(exc).__name__}: {exc}"
            out = None
            logger.warning("[IPP %s] error: %s", self.name, error)
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._observations.append({
                "name": self.name,
                "elapsed_ms": round(elapsed_ms, 2),
                "error": error,
                "ts": time.time(),
                **ctx,
            })
        return out

    @property
    def observations(self) -> list[dict]:
        return list(self._observations)

    # ── Compositional closure: B∘A ────────────────────────────────────────
    def then(self, other: "IPP[O, Any]") -> "IPP[I, Any]":
        """Compose: return a new IPP that runs self then other (B∘A)."""
        f, g = self, other

        class _Chain(IPP[I, Any]):
            name = f"{f.name}->{g.name}"

            def transform(self, inp: I) -> Any:
                return g.transform(f.transform(inp))

        return _Chain()

    def __repr__(self) -> str:
        return f"IPP({self.name})"


# ══════════════════════════════════════════════════════════════════════════════
# ToolResult — the output envelope of every tool IPP
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class ToolResult:
    """Structured output of a tool invocation (matches the IPP output space)."""

    content: str = ""
    ok: bool = True
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def ok(content: Any = "", **meta) -> "ToolResult":
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)
        return ToolResult(content=content, ok=True, metadata=meta)

    @staticmethod
    def fail(message: str, **meta) -> "ToolResult":
        return ToolResult(content="", ok=False, error=str(message), metadata=meta)

    def __str__(self) -> str:
        if not self.ok:
            return f"[ERROR] {self.error}"
        return self.content


# ══════════════════════════════════════════════════════════════════════════════
# Convenience: quick IPP wrapper for plain functions
# ══════════════════════════════════════════════════════════════════════════════


def as_ipp(name: str, fn: Callable[[I], O]) -> IPP[I, O]:
    """Wrap a plain function as an IPP (Input → Φ → Output)."""
    return IPP(name=name, phi=fn) if False else _FuncIPP(name=name, fn=fn)


class _FuncIPP(IPP[I, O]):
    def __init__(self, name: str, fn: Callable[[I], O]):
        super().__init__()
        self.name = name
        self._fn = fn

    def transform(self, inp: I) -> O:
        return self._fn(inp)
