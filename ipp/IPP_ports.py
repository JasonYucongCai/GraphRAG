"""
ipp.IPP_ports — Ports (Π = Φ × A × T) and the ten-layer payload Envelope.

Per IPP v0.2.8 §2.2–2.3:

  Π := Φ × A × T
    Φ — core flow   (Λ1 payload, Λ2 metadata, Λ3 control/status)
    A — accommodation (Λ4 routing/addressing, Λ7 policies/QoS)
    T — template    (Λ6 schema/template)

The Envelope is the information unit that crosses boundaries. Executors
stamp layers Λ3–Λ10 onto it; Objects read Λ1/Λ2 and may consult the rest.
Internal edges carry Envelope copies — never state (Invariant I17).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Λ5: integrity (hash) helper ─────────────────────────────────────────────
def payload_hash(payload: Any, algorithm: str = "sha256") -> str:
    """Canonical hash of an arbitrary JSON-serialisable payload (Λ5)."""
    try:
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          default=str)
    except (TypeError, ValueError):
        blob = str(payload)
    h = hashlib.new(algorithm)
    h.update(blob.encode("utf-8"))
    return h.hexdigest()


@dataclass
class Port:
    """A structural contract at an information boundary: Π = Φ × A × T."""

    logical_type: str
    description: str = ""
    schema: Optional[dict] = None          # Λ6 — template factor T

    # ── Φ (core flow) ─────────────────────────────────────────────────────
    def core_flow(self) -> dict:
        return {
            "payload": self.logical_type,          # Λ1
            "metadata": {"content_type": self.logical_type},   # Λ2
            "control_status": {"status": "open"},  # Λ3
        }

    # ── A (accommodation) ─────────────────────────────────────────────────
    def accommodation(self) -> dict:
        return {
            "routing": {"from": None, "to": None},   # Λ4
            "policies": {"qos": "default"},           # Λ7
        }

    # ── T (template) ──────────────────────────────────────────────────────
    def template(self) -> dict:
        return {"schema": self.schema}               # Λ6

    def to_dict(self) -> dict:
        return {
            "logical_type": self.logical_type,
            "description": self.description,
            "schema": self.schema,
        }

    @classmethod
    def from_decl(cls, decl: dict) -> "Port":
        return cls(
            logical_type=decl.get("logical_type", "any"),
            description=decl.get("description", ""),
            schema=decl.get("schema"),
        )

    # Invariant I7: the three factors are present and orthogonal
    def factors(self) -> dict:
        return {
            "core_flow": self.core_flow(),
            "accommodation": self.accommodation(),
            "template": self.template(),
        }


@dataclass
class Envelope:
    """The ten-layer information unit crossing a port boundary."""

    # Λ1 payload — the actual content
    payload: Any = None
    # Λ2 metadata
    content_type: str = "any"
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%S"))
    # Λ3 control / status
    status: str = "created"
    session_id: str = ""
    channel_id: str = ""
    source: str = "external"            # external | internal
    source_channel_id: Optional[str] = None
    # Λ4 routing / addressing
    routing: dict = field(default_factory=dict)
    # Λ5 integrity
    checksum_in: str = ""
    checksum_out: str = ""
    # Λ6 schema / template
    schema: Optional[dict] = None
    # Λ7 policies / QoS
    policies: dict = field(default_factory=dict)
    # Λ8 provenance / audit
    audit_log: list = field(default_factory=list)
    processed_by: str = ""
    # Λ9 error / fallback
    error_code: Optional[str] = None
    fallback_to: Optional[str] = None
    # Λ10 edge / topology
    edge_inventory: dict = field(default_factory=dict)
    internal_traversals: list = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Any, channel_id: str = "",
                     session_id: str = "", source: str = "external",
                     source_channel_id: Optional[str] = None,
                     policies: Optional[dict] = None,
                     schema: Optional[dict] = None) -> "Envelope":
        return cls(
            payload=payload,
            content_type=type(payload).__name__,
            channel_id=channel_id,
            session_id=session_id or f"ipp-{int(time.time() * 1000)}",
            source=source,
            source_channel_id=source_channel_id,
            policies=policies or {},
            schema=schema,
        )

    def copy(self) -> "Envelope":
        """Deep-ish copy for internal-edge dispatch (I17: payload copy, no state)."""
        return Envelope(
            payload=self.payload,
            content_type=self.content_type,
            created_at=self.created_at,
            status=self.status,
            session_id=self.session_id,
            channel_id=self.channel_id,
            source=self.source,
            source_channel_id=self.source_channel_id,
            routing=dict(self.routing),
            checksum_in=self.checksum_in,
            checksum_out=self.checksum_out,
            schema=self.schema,
            policies=dict(self.policies),
            audit_log=list(self.audit_log),
            processed_by=self.processed_by,
            error_code=self.error_code,
            fallback_to=self.fallback_to,
            edge_inventory=dict(self.edge_inventory),
            internal_traversals=list(self.internal_traversals),
        )

    def to_dict(self) -> dict:
        return {
            "payload": self.payload,
            "metadata": {"content_type": self.content_type,
                         "created_at": self.created_at},
            "control_status": {"status": self.status,
                               "session_id": self.session_id,
                               "channel_id": self.channel_id,
                               "source": self.source,
                               "source_channel_id": self.source_channel_id},
            "routing": self.routing,
            "integrity": {"checksum_in": self.checksum_in,
                          "checksum_out": self.checksum_out},
            "schema": self.schema,
            "policies": self.policies,
            "provenance": {"audit_log": self.audit_log,
                           "processed_by": self.processed_by},
            "error": {"error_code": self.error_code,
                      "fallback_to": self.fallback_to},
            "edge_topology": {"inventory": self.edge_inventory,
                              "internal_traversals": self.internal_traversals},
        }


@dataclass
class GuardedOutput:
    """The Executor's guarded result: output payload + execution record."""

    payload: Any
    record: dict = field(default_factory=dict)
    envelope: Optional[Envelope] = None
