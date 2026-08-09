"""
IPP — the Information Process Protocol v0.2.8 runtime (main package).

Implements the formal model of IPP_v0.2.8_Specification.md:

  𝔉 — IPP Json File          IPP.IPP_file      (declarative specification)
  𝒢 — Graph Context          IPP.IPP_registry  (external topology context)
  Γ — IPP Constructor        IPP.IPP_constructor (the independent agent)
  Ω — IPP Object             IPP.IPP_object    (the node: computation)
  Ξ — IPP Executor           IPP.IPP_executor  (the edge: guardrails + topology)
  Π — Ports / Envelope       IPP.IPP_ports     (Φ × A × T, ten layers)
  ✓ — 17 invariants          IPP.IPP_verify

Every component of the GraphRAG project (LLMs, codex engines, tool suites)
is declared as an IPP Json File and constructed into (Ω_k, Ξ_k) peers by Γ.
"""
from IPP.IPP_constructor import IPPConstructor, IPPNode
from IPP.IPP_executor import IPPExecutor
from IPP.IPP_file import IPPFile, IPPValidationError
from IPP.IPP_object import IPPObject
from IPP.IPP_ports import Envelope, GuardedOutput, Port, payload_hash
from IPP.IPP_registry import GraphContext, RegistryEntry
from IPP.IPP_schema import IPP_JSON_SCHEMA, IPP_SCHEMA_URI, IPP_VERSION
from IPP.IPP_verify import verify_all, verify_node

__version__ = "0.2.8"

__all__ = [
    "IPPConstructor", "IPPNode", "IPPExecutor", "IPPFile", "IPPObject",
    "Envelope", "GuardedOutput", "Port", "payload_hash",
    "GraphContext", "RegistryEntry", "IPP_JSON_SCHEMA", "IPP_SCHEMA_URI",
    "IPP_VERSION", "IPPValidationError", "verify_node", "verify_all",
]
