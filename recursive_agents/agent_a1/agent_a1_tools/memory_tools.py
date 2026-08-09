"""
agent_a1_tools.memory_tools — Memory & State tools (5 tools)

memory_read, memory_write, memory_list, memory_delete, memory_search
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any
from .tool_base import MemoryTool, ReadOnlyTool, ToolContext, ToolResult


MEMORY_DIR = "recursive_agents/graph_data/memory"


def _memory_path(ctx: ToolContext) -> Path:
    root = Path(ctx.workspace_root) if ctx.workspace_root else Path(".")
    return root / MEMORY_DIR


def _mem_file(ctx: ToolContext) -> Path:
    d = _memory_path(ctx)
    d.mkdir(parents=True, exist_ok=True)
    return d / "agent_memory.json"


def _load(ctx: ToolContext) -> dict:
    f = _mem_file(ctx)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(ctx: ToolContext, data: dict) -> None:
    _mem_file(ctx).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")


class MemoryReadTool(ReadOnlyTool):
    tool_name = "memory_read"
    category = "memory"
    description = "Read a value from persistent agent memory. Use key='*' to list all keys."
    tool_schema = {
        "type": "object", "required": ["key"],
        "properties": {
            "key": {"type": "string", "description": "Key to read, or '*' for all."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        key = args.get("key", "*")
        data = _load(ctx)
        if key == "*":
            lines = [f"- `{k}`: {str(v)[:80]}" for k, v in sorted(data.items())]
            return ToolResult.success("\n".join(lines) if lines else "(empty)",
                                      key_count=len(data))
        val = data.get(key)
        if val is None:
            return ToolResult.success(f"No entry for {key!r}")
        return ToolResult.success(str(val), key=key)


class MemoryWriteTool(MemoryTool):
    tool_name = "memory_write"
    category = "memory"
    description = "Write a value to persistent agent memory."
    tool_schema = {
        "type": "object", "required": ["key", "value"],
        "properties": {
            "key": {"type": "string", "description": "Key to write."},
            "value": {"type": "string", "description": "Value to store."},
            "ttl": {"type": "number", "description": "Time-to-live in seconds."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        key = args.get("key", "")
        value = args.get("value", "")
        ttl = int(args.get("ttl", 0))
        if not key:
            return ToolResult.fail("key is required")
        data = _load(ctx)
        data[key] = {"_value": value, "_created": time.time(),
                     "_ttl": ttl}
        _save(ctx, data)
        return ToolResult.success(f"Stored: {key!r}", key=key)


class MemoryListTool(ReadOnlyTool):
    tool_name = "memory_list"
    category = "memory"
    description = "List all memory entries with metadata."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        data = _load(ctx)
        now = time.time()
        lines = []
        for k, v in sorted(data.items()):
            ttl = v.get("_ttl", 0)
            created = v.get("_created", 0)
            expires = " (expired)" if (ttl and created + ttl < now) else ""
            lines.append(f"- `{k}`: {str(v.get('_value', v))[:80]}{expires}")
        return ToolResult.success("\n".join(lines) if lines else "(empty)",
                                  key_count=len(data))


class MemoryDeleteTool(MemoryTool):
    tool_name = "memory_delete"
    category = "memory"
    description = "Delete a memory entry."
    tool_schema = {
        "type": "object", "required": ["key"],
        "properties": {"key": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        key = args.get("key", "")
        data = _load(ctx)
        if key in data:
            del data[key]
            _save(ctx, data)
            return ToolResult.success(f"Deleted: {key!r}", key=key)
        return ToolResult.fail(f"Key not found: {key!r}")


class MemorySearchTool(ReadOnlyTool):
    tool_name = "memory_search"
    category = "memory"
    description = "Search memory entries by substring."
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {"query": {"type": "string"}},
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "").lower()
        data = _load(ctx)
        matches = {k: v for k, v in data.items()
                   if query in str(v).lower()}
        lines = [f"- `{k}`: {str(v)[:80]}" for k, v in sorted(matches.items())]
        return ToolResult.success("\n".join(lines) if lines else f"No matches for {query!r}",
                                  query=query, match_count=len(matches))


def register_memory_tools(toolkit) -> None:
    toolkit.register_many([
        MemoryReadTool(), MemoryWriteTool(), MemoryListTool(),
        MemoryDeleteTool(), MemorySearchTool(),
    ])
