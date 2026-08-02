"""
tools.ipp — Information Processing Protocol (IPP) core.

Implements the formal IPP abstraction from the Codex Local architecture:

    IPP = (I, Φ, O),   Φ : I → O

Every component (LLM provider, agent engine, tool, knowledge graph query,
encoder, growth operator) is an IPP. Compositional closure: if A and B are
IPPs then B∘A is an IPP — the output of one feeds the input of the next.

Also implements the four-phase tool lifecycle used by the production tool
pipeline (resolve → validate → prepare → invoke), the ToolResult envelope,
and a decentralized ToolRegistry (side-effect registration, no central
coordinator) — matching the IPP/KGP design in the Codex Local analysis.
"""
from __future__ import annotations

import enum
import inspect
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar, Union

logger = logging.getLogger("tools.ipp")

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

    name: str = "ipp"

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


@dataclass
class ToolContext:
    """Per-invocation context passed through the four-phase pipeline."""

    workspace_root: str = ""
    session_id: str = ""
    node_id: Any = None            # the graph node the agent is operating on
    local_graph: Any = None        # materialized local graph (L_3(u))
    encoder: Any = None            # encoder layer IPP
    agent: Any = None              # back-reference to the owning agent
    extra: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# BaseTool — the four-phase tool lifecycle (resolve → validate → prepare → invoke)
# ══════════════════════════════════════════════════════════════════════════════


class BaseTool(IPP[dict, ToolResult], ABC):
    """
    Abstract tool with the production four-phase lifecycle:

      1. resolve_input(args, ctx)   — fix common LLM parameter errors
      2. validate_input(args, ctx)  — JSON-Schema validation
      3. prepare_invocation(args, ctx) — user confirmation (dangerous ops)
      4. invoke(args, ctx)          — the actual execution (abstract)

    Tools are IPPs: their input is the argument dict, their Φ is the whole
    lifecycle, their output is a ToolResult. Tools self-register in the
    ToolRegistry at instantiation (decentralized side-effect registration).
    """

    tool_name: str = "unnamed"
    tool_schema: dict = {"type": "object", "properties": {}, "required": []}
    deferred: bool = False
    category: str = "general"
    description: str = ""

    def __init__(self) -> None:
        super().__init__(phi=self._lifecycle)
        self.name = self.tool_name
        if not self.description:
            self.description = self.tool_schema.get("description", self.tool_name)
        ToolRegistry.register(self)  # side-effect registration (decentralized)

    # ── lifecycle ─────────────────────────────────────────────────────────
    def _lifecycle(self, args: dict) -> ToolResult:
        return self._run_lifecycle(args, ToolContext())

    def _run_lifecycle(self, args: dict, ctx: ToolContext) -> ToolResult:
        # Phase 1: resolve (fix LLM mistakes)
        try:
            args = self.resolve_input(args, ctx)
        except Exception as exc:
            return ToolResult.fail(f"resolve_input failed: {exc}")

        # Phase 2: validate
        errors = self.validate_input(args, ctx)
        if errors:
            return ToolResult.fail(
                f"Invalid arguments: {'; '.join(errors)}",
                validation=errors,
            )

        # Phase 3: prepare (confirmation for dangerous operations)
        try:
            confirm = self.prepare_invocation(args, ctx)
        except Exception as exc:
            return ToolResult.fail(f"prepare_invocation failed: {exc}")
        if confirm:
            ctx.extra.setdefault("confirmations", []).append(confirm)

        # Phase 4: invoke
        try:
            return self.invoke(args, ctx)
        except Exception as exc:  # noqa: BLE001 — structured errors, never raise
            logger.error("Tool %s invoke failed: %s", self.tool_name, exc)
            return ToolResult.fail(f"{type(exc).__name__}: {exc}")

    # ── overridable phases ────────────────────────────────────────────────
    def resolve_input(self, args: dict, ctx: ToolContext) -> dict:
        return args

    def validate_input(self, args: dict, ctx: ToolContext) -> list[str]:
        """Return a list of human-readable validation errors (empty = valid)."""
        props = self.tool_schema.get("properties", {})
        required = self.tool_schema.get("required", [])
        errors: list[str] = []
        for req in required:
            if req not in args or args[req] in (None, ""):
                errors.append(f"missing required field '{req}'")
        for key, val in args.items():
            prop = props.get(key, {})
            ptype = prop.get("type")
            if ptype == "integer" and not isinstance(val, (int, float)):
                errors.append(f"'{key}' must be integer")
            elif ptype == "string" and not isinstance(val, str):
                errors.append(f"'{key}' must be string")
            elif ptype == "array" and not isinstance(val, list):
                errors.append(f"'{key}' must be array")
        return errors

    def prepare_invocation(self, args: dict, ctx: ToolContext) -> Optional[str]:
        """Return a confirmation prompt string for dangerous ops, or None."""
        return None

    @abstractmethod
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        ...

    # ── IPP metadata ──────────────────────────────────────────────────────
    def definition(self) -> dict:
        """OpenAI function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.tool_schema,
            },
        }

    def __repr__(self) -> str:
        return f"<Tool {self.tool_name} deferred={self.deferred}>"


# ══════════════════════════════════════════════════════════════════════════════
# ToolRegistry — decentralized discovery (no central coordinator)
# ══════════════════════════════════════════════════════════════════════════════


class ToolRegistry:
    """O(1) name → tool lookup. Tools register themselves (side effects)."""

    _tools: dict[str, BaseTool] = {}
    _model_specific: dict[str, dict[str, BaseTool]] = {}

    @classmethod
    def register(cls, tool: BaseTool, model_id: Optional[str] = None) -> None:
        if model_id:
            cls._model_specific.setdefault(model_id, {})[tool.tool_name] = tool
        else:
            cls._tools[tool.tool_name] = tool

    @classmethod
    def get(cls, name: str, model_id: Optional[str] = None) -> Optional[BaseTool]:
        if model_id:
            tool = cls._model_specific.get(model_id, {}).get(name)
            if tool:
                return tool
        return cls._tools.get(name)

    @classmethod
    def all(cls) -> list[BaseTool]:
        return list(cls._tools.values())

    @classmethod
    def definitions(cls, round_index: int = 1) -> list[dict]:
        """Definitions for the current LLM round (deferred tools from round 2)."""
        out = []
        for tool in cls._tools.values():
            if tool.deferred and round_index < 2:
                continue
            out.append(tool.definition())
        return out

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._tools.keys())

    @classmethod
    def execute(
        cls,
        name: str,
        args: dict,
        ctx: Optional[ToolContext] = None,
        model_id: Optional[str] = None,
    ) -> ToolResult:
        tool = cls.get(name, model_id)
        if tool is None:
            return ToolResult.fail(f"Unknown tool: {name!r}")
        return tool._run_lifecycle(args or {}, ctx or ToolContext())


# ══════════════════════════════════════════════════════════════════════════════
# ToolCallEvent — observable execution trace (the agent loop's event stream)
# ══════════════════════════════════════════════════════════════════════════════


class ToolCallEvent:
    """Emitted at every key node of the agent loop, forming an auditable trace."""

    def __init__(
        self,
        type: str,  # start|tool_call|tool_result|text|approval|compaction|done|error
        tool: Optional[str] = None,
        args: Optional[dict] = None,
        content: Optional[str] = None,
        rounds: Optional[int] = None,
        usage: Optional[dict] = None,
        error: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        import time as _time

        self.type = type
        self.tool = tool
        self.args = args
        self.content = content
        self.rounds = rounds
        self.usage = usage
        self.error = error
        self.timestamp = timestamp or _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime())

    def __repr__(self) -> str:
        return f"<ToolCallEvent {self.type} tool={self.tool} content={str(self.content)[:60]!r}>"


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
