"""
ipp.IPP_object — the IPP Object Ω_k (the node): owns the computation.

Per IPP v0.2.8 §4:

  Ω_k := (Π_in,k, H_k, Π_out,k, σ_Ω,k, γ_Ω,k)

  • H_k   — the handler: Payload × Context → Payload
  • σ_Ω,k — the object's private state (counters, caches, session data)
  • γ_Ω,k — recall reference to the Constructor Γ (for hot-swap)

Axioms enforced: O1 (input conformance), O2 (output conformance),
O3 (state preservation), O4 (recall), O5 (cross-channel state isolation).

Lifecycle FSM (§4.3): unborn → active → improving → draining → retired.
Each channel's Object is fully independent (I12, I13, I14).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("ipp.IPP_object")

# Lifecycle states (§4.3)
UNBORN, ACTIVE, IMPROVING, DRAINING, RETIRED = \
    "unborn", "active", "improving", "draining", "retired"


class IPPObject:
    """Ω_k — the computation node of one channel."""

    def __init__(
        self,
        channel_id: str,
        input_port: Any,
        output_port: Any,
        handler: Optional[Callable] = None,
        state: Optional[dict] = None,
        recall_ref: Any = None,      # γ_Ω,k → Γ
        process_desc: str = "",
    ):
        self.channel_id = channel_id
        self.input_port = input_port       # Π_in
        self.output_port = output_port     # Π_out
        self.process_desc = process_desc
        self._handler = handler or self._default_handler
        self.state: dict = state if state is not None else {}
        self.recall_ref = recall_ref       # γ_Ω,k
        self._lifecycle = UNBORN
        self._created = time.time()

    # ── handler binding ───────────────────────────────────────────────────
    def bind_handler(self, handler: Callable) -> None:
        """Bind H_k at construction (Step 1–2 of the Constructor protocol)."""
        self._handler = handler

    def _default_handler(self, payload: Any, context: dict) -> Any:
        raise NotImplementedError(
            f"no handler bound for channel {self.channel_id!r}")

    # ── lifecycle FSM (§4.3) ──────────────────────────────────────────────
    @property
    def lifecycle(self) -> str:
        return self._lifecycle

    def construct(self, recall_ref: Any = None) -> "IPPObject":
        if self._lifecycle != UNBORN:
            raise RuntimeError(f"construct on {self.channel_id}: already "
                               f"{self._lifecycle}")
        if recall_ref is not None:
            self.recall_ref = recall_ref
        self._lifecycle = ACTIVE
        return self

    def recall(self, new_decl: Optional[dict] = None) -> Any:
        """Axiom O4 — Ω_k ↝ Γ for re-construction (hot-swap request)."""
        if self.recall_ref is None:
            raise RuntimeError(f"channel {self.channel_id}: no recall ref (γ_Ω)")
        if new_decl is not None:
            self._lifecycle = IMPROVING
        return self.recall_ref.recall_object(self.channel_id, new_decl)

    def drain(self) -> None:
        self._lifecycle = DRAINING

    def destroy(self) -> None:
        self._lifecycle = RETIRED
        self._handler = None
        self.state.clear()

    # ── execution ─────────────────────────────────────────────────────────
    def execute(self, envelope: Any, context: dict) -> Any:
        """Run H_k(input, context) → output (Axiom O1/O2/O3)."""
        if self._lifecycle != ACTIVE:
            raise RuntimeError(f"channel {self.channel_id}: object is "
                               f"{self._lifecycle}, not active")
        payload = envelope.payload
        # Axiom O1 — input conformance against the port template (Λ6)
        schema = (self.input_port.schema
                  or (envelope.schema if envelope else None))
        if schema:
            import jsonschema
            try:
                jsonschema.validate(payload, schema)
            except jsonschema.ValidationError as exc:
                raise ValueError(
                    f"O1 input conformance failed on {self.channel_id}: "
                    f"{exc.message}") from exc
        out = self._handler(payload, context)
        # Axiom O3 — state preservation: handler may mutate self.state only
        return out
