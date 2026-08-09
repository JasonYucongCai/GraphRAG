"""
IPP.IPP_executor — the IPP Executor Ξ_k (edge connector / runtime enforcer).

Per IPP v0.2.8 §5:

  Ξ_k := (ι_k, π_k, ρ_k, ε_k, τ*_k, γ_Ξ,k)

Guardrail envelope (Axiom X1 — no bypass path):

    ι_pre → π → [Ω_k.execute] → ι_post → ρ → τ*_dispatch

  • ι_pre   integrity: payload hash + schema validation
  • π       policy:    rate limit, latency cap, security clearance
  • Ω_k     object:    the handler (invoked through the envelope)
  • ι_post  integrity: fresh output checksum attached (Λ5)
  • ρ       provenance: append-only hash-chained audit record (Axiom X3/X9)
  • τ*      topology:   route to external D* and internal I_out targets
                        (Axiom X8 flow control: blocking / non_blocking /
                        callback); refuses external writes (X6)

Axioms: X1 no bypass, X2 fail-safe (retry/fallback/escalate), X3 audit
immutability, X4 recall, X5 topology conformance, X6 no in-band topology
mutation, X7 cross-channel guardrail isolation, X8 internal flow control,
X9 internal-edge provenance.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

from IPP.IPP_object import IPPObject, ACTIVE
from IPP.IPP_ports import Envelope, GuardedOutput, payload_hash

logger = logging.getLogger("IPP.IPP_executor")

# Error modes per Axiom X2
RETRY, FALLBACK, ESCALATE = "retry", "fallback", "escalate"

# Flow-control modes (Definition 18)
BLOCKING, NON_BLOCKING, CALLBACK = "blocking", "non_blocking", "callback"


class PolicyDenied(Exception):
    """π_k rejected the invocation (policy violation)."""


class IntegrityRejected(Exception):
    """ι_k rejected the payload (corrupted / schema violation)."""


class CircuitOpen(Exception):
    """ε_k circuit breaker is open."""


class IPPExecutor:
    """Ξ_k — the guardrail envelope + edge topology for one channel."""

    def __init__(
        self,
        channel_id: str,
        object_: IPPObject,
        decl: dict,
        recall_ref: Any = None,
        node_id: str = "",
    ):
        self.channel_id = channel_id
        self.object = object_              # Ω_k (cooperation, not coupling)
        self.node_id = node_id
        self.recall_ref = recall_ref       # γ_Ξ,k

        # ── guards from F (Steps 3–4) ─────────────────────────────────────
        self.decl = decl
        self.integrity: dict = decl.get("integrity", {})
        self.policy: dict = decl.get("policy", {})
        self.provenance: dict = decl.get("provenance", {})
        self.error_handling: dict = decl.get("error_handling", {})
        self.capabilities: dict = decl.get("edge_capabilities", {})
        self._audit_level = self.provenance.get("audit_level", "full")

        # ── τ*_k — realized topology (built by Γ, never serialized) ───────
        self.upstream: list = []           # U*_k
        self.downstream: list = []         # D*_k
        self.internal_out: list = []       # I_out_k
        self.internal_in: list = []        # I_in_k
        self._external_callbacks: list = []   # registered downstream hooks
        self._topology_locked = False      # X6: immutable in-band

        # ── ε_k runtime state ─────────────────────────────────────────────
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._last_call_ts = 0.0

        # ── ρ_k audit (hash-chained, Axiom X3) ────────────────────────────
        self.audit_log: list[dict] = []
        self._prev_hash = "0" * 64
        self._seq = 0
        self._chain_ok = True
        self._envelope_path = True         # I2: single envelope path

    # ══════════════════════════════════════════════════════════════════════
    # τ* — topology (built by Γ at Step 5/6; X5/X6 conformance)
    # ══════════════════════════════════════════════════════════════════════
    def install_topology(self, upstream: list, downstream: list,
                         internal_out: list, internal_in: list) -> None:
        """Constructor-time wiring (Step 5–6). Refuses later mutation (X6)."""
        if self._topology_locked:
            raise RuntimeError(f"{self.node_id}/{self.channel_id}: τ* already "
                               "installed — re-wiring requires recall (X6)")
        self.upstream = list(upstream)
        self.downstream = list(downstream)
        self.internal_out = list(internal_out)
        self.internal_in = list(internal_in)
        self._topology_locked = True

    def set_topology(self, *args, **kwargs) -> None:
        """X6 — external topology writes are forbidden in-band."""
        raise PermissionError(
            f"{self.node_id}/{self.channel_id}: τ* is immutable during "
            "execution (Axiom X6); use γ_Ξ ↝ Γ to re-resolve")

    def register_external_hook(self, callback: Callable) -> None:
        """Optional external dispatch target (registered by Γ/resolution)."""
        if not self._topology_locked:
            self._external_callbacks.append(callback)

    # ══════════════════════════════════════════════════════════════════════
    # The guardrail envelope (Axiom X1 — the ONLY execution path)
    # ══════════════════════════════════════════════════════════════════════
    def invoke(self, payload: Any, context: Optional[dict] = None,
               envelope: Optional[Envelope] = None,
               source_channel: Optional[str] = None) -> GuardedOutput:
        """ι_pre → π → Ω → ι_post → ρ → τ* (no bypass)."""
        context = context or {}
        if envelope is None:
            envelope = Envelope.from_payload(
                payload, channel_id=self.channel_id,
                policies=self.policy, schema=self.object.input_port.schema)
        envelope.channel_id = self.channel_id
        if source_channel:
            envelope.source = "internal"
            envelope.source_channel_id = source_channel
            envelope.internal_traversals.append(
                {"edge": f"{source_channel}->{self.channel_id}",
                 "ts": time.time()})

        try:
            # ── 1. ι_pre : integrity ─────────────────────────────────────
            self._envelope_path = True
            self._integrity_pre(envelope)
            # ── 2. π : policy ────────────────────────────────────────────
            self._policy_check(envelope)
            # ── 3. Ω_k : execute ─────────────────────────────────────────
            out = self.object.execute(envelope, context)
            # ── 4. ι_post : output integrity ─────────────────────────────
            env_out = self._integrity_post(out, envelope)
            # ── 5. ρ : provenance (hash-chained record) ──────────────────
            record = self._provenance(envelope, out, "ok")
            # ── 6. τ* : dispatch (external + internal) ───────────────────
            # blocking internal edges suspend the source and return the
            # target's guarded output as the pipeline result (§5.5)
            pipeline = self._dispatch(env_out, out, context, record)
            if pipeline is not None:
                return pipeline
            return GuardedOutput(payload=out, record=record,
                                 envelope=env_out)
        except IntegrityRejected as exc:
            return self._error_path(exc, envelope, "integrity_rejected")
        except PolicyDenied as exc:
            return self._error_path(exc, envelope, "policy_denied")
        except CircuitOpen as exc:
            return self._error_path(exc, envelope, "circuit_open")
        except Exception as exc:  # noqa: BLE001 — X2: never unhandled
            return self._error_path(exc, envelope, "handler_error")

    # ── ι ────────────────────────────────────────────────────────────────
    def _integrity_pre(self, envelope: Envelope) -> None:
        algo = self.integrity.get("checksum_algorithm", "sha256")
        envelope.checksum_in = payload_hash(envelope.payload, algo)
        schema = self.integrity.get("payload_validation_schema")
        if schema:
            import jsonschema
            try:
                jsonschema.validate(envelope.payload, schema)
            except jsonschema.ValidationError as exc:
                raise IntegrityRejected(
                    f"ι_pre: payload schema violation: {exc.message}") from exc

    def _integrity_post(self, out: Any, envelope: Envelope) -> Envelope:
        algo = self.integrity.get("checksum_algorithm", "sha256")
        env = envelope.copy()
        env.payload = out
        env.checksum_out = payload_hash(out, algo)
        env.status = "processed"
        env.processed_by = f"{self.node_id}/{self.channel_id}"
        return env

    # ── π ────────────────────────────────────────────────────────────────
    def _policy_check(self, envelope: Envelope) -> None:
        rps = int(self.policy.get("rate_limit_rps", 0))
        if rps > 0:
            now = time.time()
            if now - self._last_call_ts < 1.0 / rps:
                raise PolicyDenied(
                    f"π: rate limit {rps} rps exceeded on "
                    f"{self.channel_id}")
            self._last_call_ts = now
        # security clearance is advisory (no auth backend in this runtime)
        clearance = self.policy.get("security_clearance")
        if clearance:
            envelope.policies["security_clearance"] = clearance

    # ── ρ ────────────────────────────────────────────────────────────────
    def _record_extras(self, record: dict, envelope: Envelope,
                       out: Any) -> None:
        """Hook for subclasses to enrich the record BEFORE it is hashed."""

    def _provenance(self, envelope: Envelope, out: Any, status: str) -> dict:
        if self._audit_level == "none":
            return {}
        record = {
            "seq": self._seq,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "node": self.node_id,
            "channel": self.channel_id,
            "source": envelope.source,
            "source_channel": envelope.source_channel_id,
            "session_id": envelope.session_id,
            "checksum_in": envelope.checksum_in,
            "checksum_out": envelope.checksum_out,
            "status": status,
            "internal_traversals": list(envelope.internal_traversals),
            "prev_hash": self._prev_hash,
        }
        self._record_extras(record, envelope, out)
        # Axiom X3: hash(record_n) = H(data ∥ hash(record_{n-1}))
        self._seq += 1
        data = json.dumps(record, ensure_ascii=False, sort_keys=True,
                          default=str)
        record["record_hash"] = payload_hash(data + self._prev_hash)
        self._prev_hash = record["record_hash"]
        self.audit_log.append(record)
        envelope.audit_log.append(record["record_hash"])
        return record

    def audit_verify(self) -> bool:
        """Axiom X3 — verify the hash chain from the first record."""
        if not self.audit_log:
            return True
        prev = "0" * 64
        for r in self.audit_log:
            data = json.dumps({k: v for k, v in r.items()
                               if k != "record_hash"},
                              ensure_ascii=False, sort_keys=True, default=str)
            if payload_hash(data + prev) != r["record_hash"]:
                self._chain_ok = False
                return False
            prev = r["record_hash"]
        self._chain_ok = True
        return True

    # ── ε ────────────────────────────────────────────────────────────────
    def _error_path(self, exc: Exception, envelope: Envelope,
                    code: str) -> GuardedOutput:
        """Axiom X2 — never unhandled: retry → fallback → escalate."""
        self._consecutive_failures += 1
        envelope.error_code = code
        cb = self.error_handling.get("circuit_breaker", {})
        threshold = int(cb.get("failure_threshold", 0))
        if threshold and self._consecutive_failures >= threshold:
            recovery = int(cb.get("recovery_timeout_ms", 30000)) / 1000.0
            self._circuit_open_until = time.time() + recovery
            self._consecutive_failures = 0
        # retry loop per retry_policy
        retries = int(self.policy.get("retry_policy", {}).get("max_retries", 0))
        for attempt in range(retries):
            try:
                out = self.object.execute(envelope, {})
                self._consecutive_failures = 0
                env_out = self._integrity_post(out, envelope)
                record = self._provenance(envelope, out, f"retried({attempt})")
                return GuardedOutput(payload=out, record=record,
                                     envelope=env_out)
            except Exception as inner:  # noqa: BLE001
                logger.warning("%s/%s retry %d failed: %s",
                               self.node_id, self.channel_id,
                               attempt + 1, inner)
        # fallback / escalate
        mode = FALLBACK if self.error_handling.get("fallback_nodes") else ESCALATE
        record = self._provenance(envelope, None,
                                  f"{mode}({code})")
        logger.error("%s/%s %s: %s", self.node_id, self.channel_id,
                     mode, exc)
        return GuardedOutput(
            payload=None,
            record=record,
            envelope=envelope,
        )

    # ── τ* : dispatch (external + internal, Axiom X8 flow control) ───────
    def _dispatch(self, env_out: Envelope, out: Any, context: dict,
                  record: dict) -> Optional[GuardedOutput]:
        """Dispatch output; returns the blocking internal-edge result (if any)."""
        # external dispatch: hooks registered by Γ (conformance X5)
        for cb in self._external_callbacks:
            cb(out, context, env_out)
        # internal dispatch: I_out_k edges (Axiom X8); blocking edges return
        # the target's GuardedOutput (pipeline semantics)
        pipeline_result = None
        for edge in self.internal_out:
            r = self._dispatch_internal(edge, env_out, context)
            if r is not None and r.payload is not None:
                pipeline_result = r
        return pipeline_result

    def _dispatch_internal(self, edge: dict, env_out: Envelope,
                           context: dict) -> GuardedOutput:
        """Route a payload COPY along an internal edge (I17: no state)."""
        target_channel = edge["to"]["channel_id"]
        mode = edge.get("mode", BLOCKING)
        timeout_ms = int(edge.get("timeout_ms", 0) or 0)
        target = self.node.executors.get(target_channel)
        if target is None:
            logger.error("%s: internal target %s missing",
                         self.node_id, target_channel)
            return GuardedOutput(payload=None, record={})
        payload_copy = json.loads(
            json.dumps(env_out.payload, ensure_ascii=False, default=str))
        if mode == BLOCKING:
            t0 = time.time()
            result = target.invoke(payload_copy, context,
                                   source_channel=self.channel_id)
            if timeout_ms and time.time() - t0 > timeout_ms / 1000.0:
                env_out.error_code = "internal_timeout"
                logger.warning("%s: internal edge timeout %sms "
                               "(%s -> %s)", self.node_id, timeout_ms,
                               self.channel_id, target_channel)
            return result
        if mode == NON_BLOCKING:
            # fire-and-continue (in-process: execute in a worker thread)
            import threading
            threading.Thread(
                target=target.invoke,
                args=(payload_copy, context),
                kwargs={"source_channel": self.channel_id},
                daemon=True,
            ).start()
            return GuardedOutput(payload=None, record={})
        if mode == CALLBACK:
            def _cb(result, *_):
                target.invoke(payload_copy, context,
                              source_channel=self.channel_id)
            self._external_callbacks.append(_cb)
            return GuardedOutput(payload=None, record={})
        return GuardedOutput(payload=None, record={})

    # ── recall (Axiom X4) ─────────────────────────────────────────────────
    def recall(self, new_decl: Optional[dict] = None,
               new_context: Optional[dict] = None) -> Any:
        if self.recall_ref is None:
            raise RuntimeError(f"channel {self.channel_id}: no recall ref (γ_Ξ)")
        return self.recall_ref.recall_executor(self.channel_id, new_decl,
                                               new_context)

    def rewire(self, new_context: Optional[dict] = None) -> Any:
        """Topology re-resolution: Ξ_k ↝ Γ(𝒢') → τ*_k' (file untouched)."""
        if self.recall_ref is None:
            raise RuntimeError(f"channel {self.channel_id}: no recall ref (γ_Ξ)")
        return self.recall_ref.recall_topology(self.channel_id, new_context)

    # ── introspection ─────────────────────────────────────────────────────
    def summary(self) -> dict:
        return {
            "node": self.node_id,
            "channel": self.channel_id,
            "upstream": [f"{u[0]}.{u[1]}" for u in self.upstream],
            "downstream": [f"{d[0]}.{d[1]}" for d in self.downstream],
            "internal_out": [e["to"]["channel_id"] for e in self.internal_out],
            "internal_in": [e["from"]["channel_id"] for e in self.internal_in],
            "audit_records": len(self.audit_log),
            "audit_chain_ok": self.audit_verify(),
            "lifecycle": self.object.lifecycle,
            "topology_locked": self._topology_locked,
        }
