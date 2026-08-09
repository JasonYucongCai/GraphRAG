# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.

# ═══════════════════════════════════════════════════════════════════════════
# IPP v0.2.8 — THIS FILE REALIZES Ω (the Object) OF ONE NODE
# ═══════════════════════════════════════════════════════════════════════════
# Pipeline:  F (this folder's ipp.json) × 𝒢 ──► Γ (ipp/constructor.py)
#            ──► (Ω_k, Ξ_k) per channel — this module owns the Ω side.
#
# The Object owns the COMPUTATION layers of the ten-layer taxonomy
# (spec §7.1, Theorem 3): Λ1 Payload, Λ2 Metadata, Λ3 Control/Status,
# Λ4 Routing/Addressing, Λ6 Schema/Template — carried by the Ports
# declared in ipp.json. The ENFORCEMENT layers (Λ5 Integrity, Λ7
# Policy, Λ8 Provenance, Λ9 Error, Λ10 Topology) live in the sibling
# ipp_executor.py / ipp/executor.py.
#
# Pattern used here (the folder convention):
#   • a module-level singleton + lock → get_ipp_object() — the folder
#     owns construction; Γ is invoked once per process
#   • the class subclasses ipp.object.IPPObject and binds the folder's
#     handler H (from the sibling ipp_executor module) — H is the
#     node's core transformation: Payload × Context → Payload
#   • channel_id="default" — single-channel folders; multi-channel
#     nodes construct one object per channel (|I| = 2n + 1 peers)
#   • the registry discovers this file via register_folder()
# ═══════════════════════════════════════════════════════════════════════════
"""tools/copilot/ipp_object.py — IPP v0.2.8 IPP Object (tools.copilot toolset node)

The copilot toolset folder as a first-class IPP node — constructed per
the formal definition (§7.1–§7.4):

    tools/copilot/ipp.json ──► Γ (IPPConstructor) ──► (Ω, Ξ) for tools.copilot

Ω = the default toolset node (owns the global ToolRegistry): full
registry toolset with validation, deferral, memory, search, shell,
sub-agent and notebook tools, under the linked Executor's guardrail
envelope.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from ipp.constructor import IPPConstructor
from ipp.datatypes import IPPDefinition
from ipp.object import IPPObject
from ipp.schema import load_definition_file

NODE_ID = "tools.copilot"
_JSON_PATH = Path(__file__).resolve().parent / "ipp.json"


class CopilotToolsetIPPObject(IPPObject):
    """Ω of the tools.copilot toolset node (constructed from ipp.json)."""

    def __init__(self, definition: IPPDefinition,
                 constructor: Optional[IPPConstructor] = None,
                 handler: Optional[Callable] = None,
                 channel_id: str = "default"):
        if handler is None:
            from tools.copilot.ipp_executor import _handler
            handler = _handler
        super().__init__(definition, handler=handler,
                         constructor=constructor,
                         channel_id=channel_id)


# Module-level singleton — the folder's constructed IPP Object.
_OBJECT: Optional[CopilotToolsetIPPObject] = None
_object_lock = threading.Lock()


def get_ipp_object() -> CopilotToolsetIPPObject:
    """Construct (once) the folder's IPP Object from its ipp.json."""
    global _OBJECT
    with _object_lock:
        if _OBJECT is None:
            definition = load_definition_file(_JSON_PATH)
            obj, _ = IPPConstructor().construct(
                definition, object_cls=CopilotToolsetIPPObject,
                base_path=str(_JSON_PATH.parent))
            _OBJECT = obj
        return _OBJECT
