# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.

"""
agent_a0_tools.ipp_executor — IPP v0.2.8 Executor (Ξ_k) for agent_a0's tools.

The Executor owns the ENFORCEMENT layers of the ten-layer taxonomy (spec §7.1):
  Λ5 Integrity (ξ_decl.integrity), Λ7 Policy, Λ8 Provenance, Λ9 Error,
  Λ10 Edge/Topology (external K_τ + internal topology).

Every tool invocation flows through the guardrail envelope:
  ι_pre → π → Ω (handler) → ι_post → ρ (hash-chain audit) → τ*_dispatch.

The COMPUTATION layers (Λ1–Λ4, Λ6) live in the sibling ipp_object.py.
This module is the folder's PUBLIC IPP SURFACE — the uniform 5-function
contract every IPP folder exposes (spec §7.3):
    ipp_definition()    → F (the folder's IPP Json File)
    get_ipp_executor()  → the constructed Ξ (guardrail envelope)
    execute_ipp(payload)→ guarded execution through that envelope
    register_ipp()      → register this node in the decentralized
                          registry (GraphContext 𝒢, §3.2)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from ipp.api import (ExecutionContext, ExecutionResult, IPPDefinition,
                     IPPExecutor, get_registry)
from ipp.schema import load_definition_file

logger = logging.getLogger("tools.copilot.ipp")

NODE_ID = "tools.copilot"
ENGINE_ID = "copilot"
DEFAULT_PRESET = ""
_JSON_PATH = Path(__file__).resolve().parent / "ipp.json"


def _toolset_names(preset: str = DEFAULT_PRESET) -> set[str]:
    """The tool names in this toolset (Copilot: full registry)."""
    from tools.ipp_executor import get_engine_tools
    return set(get_engine_tools(ENGINE_ID, preset or DEFAULT_PRESET))


# ══════════════════════════════════════════════════════════════════════════════
# Handler — the Copilot toolset process realization (H of tools.copilot)
# ══════════════════════════════════════════════════════════════════════════════

def _handler(payload: dict[str, Any], context: ExecutionContext) -> Any:
    """Execute a toolset operation under the IPP guardrail."""
    operation = (payload or {}).get("operation", "")
    data = (payload or {}).get("data", {}) or {}
    preset = data.get("preset", DEFAULT_PRESET)
    allowed = _toolset_names(preset)

    if operation == "list_tools":
        return {"engine_id": ENGINE_ID, "preset": preset,
                "tools": sorted(allowed), "count": len(allowed)}

    if operation == "tool_defs":
        from tools.ipp_executor import get_engine_tool_defs, get_engine_tool_count
        return {"engine_id": ENGINE_ID, "preset": preset,
                "tool_defs": get_engine_tool_defs(ENGINE_ID, preset),
                "count": get_engine_tool_count(ENGINE_ID, preset)}

    if operation == "tool_info":
        name = data.get("tool_name", "")
        if name not in allowed:
            raise ValueError(f"tool {name!r} not in {ENGINE_ID} toolset")
        from tools.ipp_executor import get_tool_openai_defs
        for d in get_tool_openai_defs():
            if d.get("function", {}).get("name") == name:
                return {"tool_info": d}
        raise ValueError(f"unknown tool: {name!r}")

    if operation == "execute":
        name = data.get("tool_name", "")
        if name not in allowed:
            raise ValueError(f"tool {name!r} not in {ENGINE_ID} toolset")
        # Real registry execution (full lifecycle: resolve/validate/invoke)
        import asyncio
        from tools.copilot.tool_base import ToolContext
        from tools.ipp_executor import get_tool_registry
        from config import Config
        tctx = ToolContext(
            workspace_root=data.get("workspace_root")
            or str(Config.WORKSPACE_ROOT),
            session_id=data.get("session_id", ""),
            request_id=data.get("request_id", ""),
            agent_name=data.get("agent_name", "ipp"),
            cancelled=bool(data.get("cancelled", False)),
        )
        result = asyncio.run(get_tool_registry().execute_tool(
            name, data.get("arguments", {}) or {}, tctx,
            data.get("model_id", "")))
        return {"tool_name": name, "result": str(result)}

    if operation == "catalog":
        return {"catalog": {"total": len(allowed),
                            "engine": ENGINE_ID,
                            "preset": preset,
                            "tools": sorted(allowed)}}

    if operation == "count":
        return {"engine_id": ENGINE_ID, "count": len(allowed)}

    raise ValueError(f"unknown toolset operation: {operation!r}")


# ══════════════════════════════════════════════════════════════════════════════
# IPP v0.2.8 surface
# ══════════════════════════════════════════════════════════════════════════════

def ipp_definition() -> IPPDefinition:
    """Load the declarative IPP Json File for this folder (F)."""
    return load_definition_file(_JSON_PATH)


def get_ipp_executor() -> IPPExecutor:
    """The folder's constructed IPP Executor (Ξ)."""
    from tools.copilot.ipp_object import get_ipp_object
    return get_ipp_object().executor


def ipp_executor() -> IPPExecutor:
    """Register + return the tools.copilot executor (compat name)."""
    register_ipp()
    return get_ipp_executor()


def execute_ipp(payload: dict[str, Any],
                context: Optional[ExecutionContext] = None) -> ExecutionResult:
    """Execute a toolset operation through the full guardrail envelope."""
    register_ipp()
    return get_registry().execute(NODE_ID, payload, context)


def register_ipp() -> str:
    """Register the tools.copilot node in the decentralized registry."""
    get_registry().register_folder(_JSON_PATH.parent)
    return NODE_ID
