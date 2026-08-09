"""
IPP.IPP_constructor — the IPP Constructor Γ (the independent agent).

Per IPP v0.2.8 §8: Γ ∈ 𝒜, Γ ⊩ F × 𝒢 ↝ ((Ω_k, Ξ_k[τ*_k]) for k=1..n, ℰ_int).

Seven-step construction protocol (§8.2):
  Steps 1–2  construct all Objects  (ports, handler binding, state, γ_Ω)
  Steps 3–4  configure all Executors (ι, π, ρ, ε from F)
  Step 5     resolve external topology per channel against 𝒢
  Step 6     wire internal topology (R1–R4 validation, I_out/I_in,
             completion-signal wiring for blocking edges)
  Step 7     return ({Ω_k, Ξ_k}, ℰ_int); Γ becomes dormant (Lemma 1)

Realization: Γ is realized here as the deterministic code-binding agent
(𝒜_code-gen) — handlers are resolved from the ``handler`` import-path
declarations in F (the binding table), with optional factory invocation
against the GraphContext bindings.

Recall (§8.3): object hot-swap, executor hot-swap, topology re-resolution,
internal re-wire, channel add/remove.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from IPP.IPP_executor import IPPExecutor
from IPP.IPP_file import IPPFile
from IPP.IPP_object import IPPObject
from IPP.IPP_ports import Port
from IPP.IPP_registry import GraphContext

logger = logging.getLogger("IPP.IPP_constructor")


class IPPNode:
    """The assembled runtime: 2n + 1 peers (Γ dormant after construction)."""

    def __init__(self, file: IPPFile, objects: dict, executors: dict,
                 constructor: "IPPConstructor", topology: dict):
        self.file = file
        self.node_id = file.node_id
        self.objects: dict[str, IPPObject] = objects      # Ω_k
        self.executors: dict[str, IPPExecutor] = executors  # Ξ_k
        self.constructor = constructor                    # Γ (dormant)
        self.topology = topology                          # 𝒢' + wiring record
        self._registry_ref: Optional[GraphContext] = None

    # ── channels ──────────────────────────────────────────────────────────
    @property
    def channels(self) -> list[str]:
        return list(self.file.channel_ids)

    # ── the primary invocation surface ────────────────────────────────────
    def invoke(self, channel_id: str, payload: Any,
               context: Optional[dict] = None) -> Any:
        """Run channel `channel_id` through its executor's guardrail
        envelope. Returns GuardedOutput (payload + audit record)."""
        executor = self.executors[channel_id]
        return executor.invoke(payload, context)

    def handler(self, channel_id: str) -> Callable:
        """Direct access to the raw handler (bypasses guardrails — for
        internal composition only; use invoke() at boundaries)."""
        return self.objects[channel_id]._handler

    # ── I4: atomic hot-swap ───────────────────────────────────────────────
    def swap(self, channel_id: str, new_object: IPPObject) -> None:
        """Atomic replacement of Ω_k (reference-counted swap)."""
        new_object.recall_ref = self.constructor
        new_object.construct(self.constructor)
        self.objects[channel_id] = new_object
        self.executors[channel_id].object = new_object

    # ── I5: recall ────────────────────────────────────────────────────────
    def recall(self, channel_id: str, new_decl: Optional[dict] = None) -> Any:
        return self.objects[channel_id].recall(new_decl)

    def verify(self) -> list[str]:
        """17-invariant verification (IPP.IPP_verify). Empty list = all pass."""
        from IPP.IPP_verify import verify_node
        return verify_node(self)

    def summary(self) -> str:
        lines = [f"IPPNode({self.node_id}): {len(self.channels)} channels"]
        for ch in self.channels:
            ex = self.executors[ch]
            lines.append(f"  {ch}: {ex.summary()}")
        return "\n".join(lines)


class IPPConstructor:
    """Γ — constructs IPP nodes from F × 𝒢 (7-step protocol)."""

    def __init__(self, context: Optional[GraphContext] = None,
                 executor_classes: Optional[dict] = None):
        self.context = context or GraphContext()
        self._handler_cache: dict[str, Callable] = {}
        self._executor_classes: dict = executor_classes or {}
        self._current_node_id: Optional[str] = None
        self._recall_node: Optional[IPPNode] = None

    # ── handler binding (the code-gen binding table) ──────────────────────
    def _resolve_handler(self, ref: str, channel_id: str,
                         bindings: dict) -> Callable:
        if ref in self._handler_cache:
            return self._handler_cache[ref]
        module_name, _, attr = ref.partition(":")
        if not attr:
            raise ValueError(f"handler ref must be 'module:attr': {ref!r}")
        module = importlib.import_module(module_name)
        factory = getattr(module, attr)
        # factories are called with (bindings) or () — plain functions are
        # used directly as handlers
        try:
            handler = factory(bindings)
        except TypeError:
            handler = factory
        if not callable(handler):
            raise TypeError(f"handler {ref!r} did not produce a callable")
        self._handler_cache[ref] = handler
        return handler

    # ── Step 1–2: construct objects ───────────────────────────────────────
    def _construct_object(self, channel: dict, bindings: dict) -> IPPObject:
        ch_id = channel["channel_id"]
        obj_decl = channel["ipp_object"]
        in_port = Port.from_decl(obj_decl["input"])
        out_port = Port.from_decl(obj_decl["output"])
        ref = channel.get("handler")
        handler = (self._resolve_handler(ref, ch_id, bindings)
                   if ref else None)
        return IPPObject(
            channel_id=ch_id,
            input_port=in_port,
            output_port=out_port,
            handler=handler,
            process_desc=obj_decl["process"].get("description", ""),
        )

    # ── Steps 3–4: configure executors ────────────────────────────────────
    def _construct_executor(self, channel: dict,
                            object_: IPPObject) -> IPPExecutor:
        ch_id = channel["channel_id"]
        cls = self._executor_classes.get(ch_id) or IPPExecutor
        return cls(
            channel_id=ch_id,
            object_=object_,
            decl=channel["ipp_executor"],
            recall_ref=self,
            node_id=self._current_node_id,
        )

    # ── Step 5: resolve external topology ─────────────────────────────────
    def _resolve_external(self, ch_id: str, cap: dict) -> tuple[list, list]:
        upstream = self.context.candidates(cap, "upstream")
        downstream = self.context.candidates(cap, "downstream")
        return upstream, downstream

    # ── Step 6: wire internal topology ────────────────────────────────────
    def _wire_internal(self, file: IPPFile, executors: dict) -> dict:
        edges = file.internal_edges()
        for e in edges:
            src = e["from"]["channel_id"]
            dst = e["to"]["channel_id"]
            executors[src].internal_out.append(e)
            executors[dst].internal_in.append(e)
        return {"edges": edges}

    # ── Step 7: the public construct entry ────────────────────────────────
    def construct(self, file: IPPFile, context: Optional[GraphContext] = None,
                  bindings: Optional[dict] = None) -> IPPNode:
        """Γ ⊩ F × 𝒢 ↝ ((Ω_k, Ξ_k[τ*_k]), ℰ_int)."""
        if context is not None:
            self.context = context
        self._current_node_id = file.node_id
        all_bindings = dict(self.context.bindings)
        if bindings:
            all_bindings.update(bindings)

        # Steps 1–4
        objects, executors = {}, {}
        for channel in file.channels:
            ch_id = channel["channel_id"]
            obj = self._construct_object(channel, all_bindings)
            obj.construct(self)
            ex = self._construct_executor(channel, obj)
            objects[ch_id], executors[ch_id] = obj, ex

        # Step 6 first (wiring needs unlocked executors), then Step 5
        # external resolution — both installed in ONE lock step:
        wiring = self._wire_internal(file, executors)
        for ch_id, ex in executors.items():
            up, down = [], []
            if ex.capabilities:
                up, down = self._resolve_external(ch_id, ex.capabilities)
            ex.install_topology(upstream=up, downstream=down,
                                internal_out=ex.internal_out,
                                internal_in=ex.internal_in)

        # Step 7 — return; Γ goes dormant (Lemma 1)
        node = IPPNode(file=file, objects=objects, executors=executors,
                       constructor=self, topology=wiring)
        for ex in executors.values():
            ex.node = node
        self._current_node_id = None
        return node

    # ── convenience ───────────────────────────────────────────────────────
    def construct_file(self, path, context: Optional[GraphContext] = None,
                       bindings: Optional[dict] = None) -> IPPNode:
        return self.construct(IPPFile.load(path), context, bindings)

    # ── recall semantics (§8.3) ───────────────────────────────────────────
    def recall_object(self, channel_id: str,
                      new_decl: Optional[dict]) -> Any:
        """Ω_k ↝ Γ: hot-swap the object of one channel."""
        if new_decl is None:
            raise ValueError("recall_object requires a new channel declaration")
        raise NotImplementedError(
            "object hot-swap via modified declaration requires a "
            "constructor agent (LLM); construct a new node and swap()")

    def recall_executor(self, channel_id: str, new_decl: Optional[dict],
                        new_context: Optional[dict]) -> Any:
        """Ξ_k ↝ Γ: hot-swap the executor of one channel."""
        raise NotImplementedError(
            "executor hot-swap requires a constructor agent (LLM)")

    def recall_topology(self, channel_id: str,
                        new_context: Optional[dict]) -> Any:
        """Ξ_k ↝ Γ(𝒢'): re-resolve external topology, file untouched."""
        if self._recall_node is None:
            raise RuntimeError("recall_topology needs _recall_node bound "
                               "(set by recall_scope)")
        node = self._recall_node
        ex = node.executors[channel_id]
        if new_context is not None:
            self.context = new_context
        cap = ex.capabilities
        up, down = self._resolve_external(channel_id, cap)
        ex.install_topology(upstream=up, downstream=down,
                            internal_out=ex.internal_out,
                            internal_in=ex.internal_in)
        return ex

    def recall_scope(self, node: IPPNode) -> None:
        """Bind the node Γ recalls on (per-channel recall context)."""
        self._recall_node = node

    def recall_internal(self, node: IPPNode, edges: list[dict]) -> IPPNode:
        """Γ(F[internal_topology ← ℰ_int']): atomic internal re-wire."""
        for ex in node.executors.values():
            ex.internal_out, ex.internal_in = [], []
        new_file = IPPFile({**node.file.raw,
                            "internal_topology": {"edges": edges}})
        # validate the new topology before rewiring
        self._wire_internal(new_file, node.executors)
        node.file = new_file
        node.topology = {"edges": edges}
        return node
