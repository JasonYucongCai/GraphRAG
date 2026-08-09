"""
tools.catalog — the LLM tool definitions, DERIVED from the F-files.

The F-file channel input schemas (anyOf per-op branches) ARE the tool
catalog: there is no parallel BaseTool layer anymore. For each route in
tools.routes, the catalog finds the target channel declaration (the
tools node's own F-file, the database node's F-file, or the
social_activity node's F-file) and extracts the op branch:

  {name, description, schema}   — the definition the LLM sees

Built ONCE at construction time (Γ, tools.construct) and served by the
tools node's `list` / `describe` channels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from general_tools.routes import ROUTES

WS = Path(__file__).resolve().parents[1]

_FILES = {
    "self": WS / "general_tools" / "IPP.json",
    "database": WS / "database" / "IPP.json",
    "social_activity": WS / "IPP_Social" / "social_activity" / "IPP.json",
}


def _channel_decl(node_key: str, channel_id: str) -> Optional[dict]:
    path = _FILES.get(node_key)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    for ch in data.get("channels", []):
        if ch.get("channel_id") == channel_id:
            return ch
    return None


def _op_branch(schema: Optional[dict], op: Optional[str]) -> Optional[dict]:
    """The anyOf branch for `op` (or the whole schema for codex channels).

    If op is given but no anyOf branch matches, falls back to the generic
    schema (channels like a2a use mode/action as discriminator, not op).
    """
    if not schema:
        return None
    # no op → return the generic schema (codex channels, flat channels)
    if op is None:
        return {"properties": schema.get("properties", {}),
                "required": schema.get("required", [])}
    # op given → look for a matching anyOf branch
    for branch in schema.get("anyOf", []) or []:
        props = branch.get("properties", {})
        if props.get("op", {}).get("const") == op:
            return branch
    # fallback: no anyOf or no match → return the generic schema
    # (the adapter handles mode/action injection; the LLM just needs the
    # base input shape from the F-file)
    if not schema.get("anyOf"):
        return {"properties": schema.get("properties", {}),
                "required": schema.get("required", [])}
    return None


def build_catalog() -> dict:
    """{tool_name: {name, description, schema}} — from the F-files."""
    catalog: dict = {}
    for name, (node_key, channel_id, op, _adapter) in ROUTES.items():
        ch = _channel_decl(node_key, channel_id)
        if ch is None:
            continue
        obj = ch.get("ipp_object", {})
        branch = _op_branch(obj.get("input", {}).get("schema"), op)
        if branch is None:
            continue
        # the per-op description (branch) or the channel process description
        desc = branch.get("description") or \
            obj.get("process", {}).get("description", "")
        props = {k: v for k, v in branch.get("properties", {}).items()
                 if k != "op"}
        required = [r for r in branch.get("required", []) if r != "op"]
        schema = {"type": "object", "properties": props, "required": required}
        catalog[name] = {"name": name, "description": desc, "schema": schema}
    return catalog


def names(catalog: dict) -> list[str]:
    return sorted(catalog)


def definition(catalog: dict, name: str) -> Optional[dict]:
    entry = catalog.get(name)
    if entry is None:
        return None
    return {
        "type": "function",
        "function": {
            "name": entry["name"],
            "description": entry["description"],
            "parameters": entry["schema"],
        },
    }
