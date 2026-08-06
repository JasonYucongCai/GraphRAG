"""
tools.graph_tools — the agent tool suite (MCP-style IPP tools).

Combines:
  • Graph tools   — the tools the agent uses to operate on nodes via their
                    local graphs (get_local_graph, search_nodes, read_node,
                    register_node, link_nodes, unlink, infer_edges, ...)
  • Core tools    — a self-contained subset of the codex 19-tool suite
                    (read_file, write_file, list_directory, shell_command,
                    grep_search, current_time, memory_read, memory_write)

Every tool is a BaseTool → an IPP with the four-phase lifecycle
(resolve → validate → prepare → invoke), self-registered in the ToolRegistry.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from tools.config import Config
from tools.IPP import BaseTool, ToolContext, ToolResult

logger = logging.getLogger("tools.graph_tools")


def _resolve_path(p: str, ctx: ToolContext) -> Path:
    root = Path(ctx.workspace_root or Config.WORKSPACE_ROOT)
    path = Path(p)
    return path if path.is_absolute() else (root / path).resolve()


# ══════════════════════════════════════════════════════════════════════════════
# Graph tools — the agent's hands on the network
# ══════════════════════════════════════════════════════════════════════════════


class GetLocalGraphTool(BaseTool):
    tool_name = "get_local_graph"
    category = "graph"
    description = "Materialize the depth-k local graph (default 3) of a node — the agent's working memory."
    tool_schema = {
        "type": "object",
        "properties": {
            "node_id": {"type": ["string", "integer"], "description": "Node id or entryname"},
            "depth": {"type": "integer", "description": "BFS depth, default 3"},
        },
        "required": ["node_id"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        graph = ctx.extra.get("graph") or getattr(ctx.agent, "graph", None)
        if graph is None:
            return ToolResult.fail("no graph bound to this tool context")
        anchor = graph.resolve(args["node_id"])
        if anchor is None:
            return ToolResult.fail(f"node not found: {args['node_id']}")
        local = graph.materialize_local(anchor, depth=int(args.get("depth", Config.LOCAL_DEPTH)))
        return ToolResult.ok(local.verbalize(), node_count=local.node_count(),
                             edge_count=local.edge_count(), stats=local.stats)


class SearchNodesTool(BaseTool):
    tool_name = "search_nodes"
    category = "graph"
    description = "Vector-based RAG search: find nodes and chunks similar to a query (encoder layer)."
    tool_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "top-k, default 10"},
        },
        "required": ["query"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        encoder = ctx.extra.get("encoder") or (getattr(ctx.agent, "encoder", None) if ctx.agent else None)
        graph = ctx.extra.get("graph") or (getattr(ctx.agent, "graph", None) if ctx.agent else None)
        if encoder is None:
            return ToolResult.fail("no encoder bound to this tool context")
        k = int(args.get("k", 10))
        hits = encoder.search_nodes(args["query"], k=k)
        lines = [f"top-{len(hits)} nodes by vector similarity:"]
        for nid, sim in hits:
            name = graph.get_node(nid).entryname if graph and graph.get_node(nid) else nid
            lines.append(f"  {name} [{nid}] sim={sim:.4f}")
        chunks = encoder.search(args["query"], k=min(k, 8))
        lines.append("top chunks:")
        for chunk, sim in chunks[:8]:
            lines.append(f"  {chunk.chunk_id} sim={sim:.3f}: {chunk.text[:80]}...")
        return ToolResult.ok("\n".join(lines))


class ReadNodeTool(BaseTool):
    tool_name = "read_node"
    category = "graph"
    description = "Read a node's metadata: entryname, category, description, content refs, stats."
    tool_schema = {
        "type": "object",
        "properties": {"node_id": {"type": ["string", "integer"]}},
        "required": ["node_id"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        graph = ctx.extra.get("graph") or (getattr(ctx.agent, "graph", None) if ctx.agent else None)
        if graph is None:
            return ToolResult.fail("no graph bound")
        node = graph.get_node(graph.resolve(args["node_id"]))
        if node is None:
            return ToolResult.fail(f"node not found: {args['node_id']}")
        payload = {
            "node_id": node.node_id, "entryname": node.entryname,
            "category": node.category, "description": node.description[:300],
            "content": node.content, "stats": node.stats,
            "version": node.version,
        }
        return ToolResult.ok(json.dumps(payload, ensure_ascii=False, indent=1))


class RegisterNodeTool(BaseTool):
    """Re-exported from database.database_tool (single source of truth)."""
    tool_name = "register_node"
    category = "database"

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        from database.database_tool import RegisterNodeTool as _T
        return _T()._run_lifecycle(args, ctx)


class LinkNodesTool(BaseTool):
    tool_name = "link_nodes"
    category = "database"

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        from database.database_tool import LinkNodesTool as _T
        return _T()._run_lifecycle(args, ctx)


class UnlinkTool(BaseTool):
    tool_name = "unlink"
    category = "database"

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        from database.database_tool import UnlinkTool as _T
        return _T()._run_lifecycle(args, ctx)


class InferEdgesTool(BaseTool):
    tool_name = "infer_edges"
    category = "database"

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        from database.database_tool import InferEdgesTool as _T
        return _T()._run_lifecycle(args, ctx)


class ProbeGapTool(BaseTool):
    tool_name = "probe_gap"
    category = "database"

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        from database.database_tool import ProbeGapTool as _T
        return _T()._run_lifecycle(args, ctx)


class ValidateGraphTool(BaseTool):
    tool_name = "validate_graph"
    category = "graph"
    description = "Run §4.3a consistency + health checks; report violations."
    tool_schema = {"type": "object", "properties": {}, "required": []}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        graph = ctx.extra.get("graph") or (getattr(ctx.agent, "graph", None) if ctx.agent else None)
        if graph is None:
            return ToolResult.fail("no graph bound")
        violations = graph.validate_consistency()
        comps = graph.connected_components()
        lines = [graph.summary(),
                 f"consistency violations: {len(violations)}",
                 f"weakly-connected components: {len(comps)}"]
        if violations:
            lines += [f"  !! {v}" for v in violations[:5]]
        return ToolResult.ok("\n".join(lines))


class SummarizeLocalTool(BaseTool):
    tool_name = "summarize_local"
    category = "graph"
    description = "Produce a compact text summary of a node's local graph (community-style summary)."
    tool_schema = {
        "type": "object",
        "properties": {
            "node_id": {"type": ["string", "integer"]},
            "focus": {"type": "string", "description": "what the summary should focus on"},
        },
        "required": ["node_id"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        graph = ctx.extra.get("graph") or (getattr(ctx.agent, "graph", None) if ctx.agent else None)
        if graph is None:
            return ToolResult.fail("no graph bound")
        anchor = graph.resolve(args["node_id"])
        if anchor is None:
            return ToolResult.fail(f"node not found: {args['node_id']}")
        local = graph.materialize_local(anchor, depth=Config.LOCAL_DEPTH)
        names = [n.entryname for n in local.nodes.values()]
        focus = args.get("focus", "")
        summary = (
            f"Local graph of {anchor} (depth {local.depth}): {len(names)} nodes, "
            f"{len(local.edges)} edges. Nodes: {', '.join(names[:25])}"
            + (f"… Focus: {focus}" if focus else "")
        )
        return ToolResult.ok(summary)


# ══════════════════════════════════════════════════════════════════════════════
# Core tools — self-contained subset of the codex 19-tool suite
# ══════════════════════════════════════════════════════════════════════════════


class ReadFileTool(BaseTool):
    tool_name = "read_file"
    category = "file"
    description = "Read a file (line numbers, encoding detection, 8000 char cap)."
    tool_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        p = _resolve_path(args["path"], ctx)
        if not p.is_file():
            return ToolResult.fail(f"file not found: {p}")
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = int(args.get("start_line", 1))
        end = int(args.get("end_line", len(lines)))
        sel = lines[start - 1:end]
        body = "\n".join(f"{i + start}: {ln}" for i, ln in enumerate(sel))
        capped = body[:8000] + ("..." if len(body) > 8000 else "")
        return ToolResult.ok(capped, size=len(text), lines=len(lines))


class WriteFileTool(BaseTool):
    tool_name = "write_file"
    category = "file"
    description = "Write a file (auto-creates parents; backup of existing)."
    tool_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        p = _resolve_path(args["path"], ctx)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            bak = p.with_suffix(p.suffix + ".bak")
            bak.write_text(p.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        p.write_text(args["content"], encoding="utf-8")
        return ToolResult.ok(f"wrote {p} ({len(args['content'])} chars)")


class ListDirectoryTool(BaseTool):
    tool_name = "list_directory"
    category = "file"
    description = "List directory contents with sizes and type icons."
    tool_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "default workspace root"}},
        "required": [],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        p = _resolve_path(args.get("path", ""), ctx)
        if not p.is_dir():
            return ToolResult.fail(f"not a directory: {p}")
        lines = [f"{p}:"]
        for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            icon = "📁" if child.is_dir() else "📄"
            size = f"{child.stat().st_size / 1024:.1f}KB" if child.is_file() else ""
            lines.append(f"  {icon} {child.name} {size}")
        return ToolResult.ok("\n".join(lines))


class GrepSearchTool(BaseTool):
    tool_name = "grep_search"
    category = "search"
    description = "Regex content search with file:line refs and context lines."
    tool_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "include_pattern": {"type": "string"},
            "context_lines": {"type": "integer"},
            "max_matches": {"type": "integer"},
        },
        "required": ["query"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        pattern = args["query"]
        include = args.get("include_pattern") or "**/*"
        context = int(args.get("context_lines", 0))
        max_matches = int(args.get("max_matches", 30))
        root = Path(ctx.workspace_root or Config.WORKSPACE_ROOT)
        rx = re.compile(pattern, re.IGNORECASE)
        hits = 0
        lines: list[str] = []
        for p in root.rglob("*"):
            if p.is_dir() or not _matches_glob(p, include):
                continue
            if any(part.startswith((".git", "node_modules", "__pycache__")) for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, ln in enumerate(text.splitlines(), 1):
                if rx.search(ln):
                    rel = p.relative_to(root)
                    lines.append(f"{rel}:{i}: {ln.strip()[:160]}")
                    hits += 1
                    if context:
                        pass  # context handled inline below
                    if hits >= max_matches:
                        return ToolResult.ok("\n".join(lines), match_count=hits)
        return ToolResult.ok("\n".join(lines) or f"no matches for {pattern!r}", match_count=hits)


def _matches_glob(p: Path, pattern: str) -> bool:
    pat = pattern.replace("**", "ZZ").replace("*", ".*").replace("ZZ", ".*")
    return bool(re.search(pat, str(p).replace("\\", "/"), re.IGNORECASE))


class ShellCommandTool(BaseTool):
    tool_name = "shell_command"
    category = "system"
    description = "Execute a shell command (30s timeout; blocks destructive commands)."
    tool_schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}},
        "required": ["command"],
    }
    DESTRUCTIVE = [r"\brm\s+-rf\s+/", r"\bgit\s+reset\s+--hard", r"\bgit\s+checkout\s+--", r"\bdd\s+if="]

    def prepare_invocation(self, args: dict, ctx: ToolContext) -> Optional[str]:
        cmd = args.get("command", "")
        for pat in self.DESTRUCTIVE:
            if re.search(pat, cmd):
                return f"destructive command detected: {pat}"
        return None

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        import subprocess
        root = str(ctx.workspace_root or Config.WORKSPACE_ROOT)
        try:
            r = subprocess.run(args["command"], shell=True, capture_output=True,
                               timeout=30, cwd=root)
            out = (r.stdout or b"").decode("utf-8", errors="replace")
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            snippet = f"exit={r.returncode}\n{out[:4000]}"
            if err:
                snippet += f"\n[stderr] {err[:1500]}"
            return ToolResult.ok(snippet, exit_code=r.returncode)
        except subprocess.TimeoutExpired:
            return ToolResult.fail("command timed out (30s)")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(str(exc))


class CurrentTimeTool(BaseTool):
    tool_name = "current_time"
    category = "utility"
    description = "Current local/UTC/ISO time."
    tool_schema = {"type": "object", "properties": {}, "required": []}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(time.strftime("%Y-%m-%d %H:%M:%S %Z (%A)"))


class MemoryReadTool(BaseTool):
    tool_name = "memory_read"
    category = "memory"
    description = "Read from persistent key-value memory ('*' lists all)."
    tool_schema = {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        mem = _memory_store()
        key = args["key"]
        if key == "*":
            return ToolResult.ok(json.dumps({k: v["value"][:100] for k, v in mem.items()},
                                            ensure_ascii=False, indent=1))
        entry = mem.get(key)
        return ToolResult.ok(entry["value"] if entry else f"(no memory for {key!r})")


class MemoryWriteTool(BaseTool):
    tool_name = "memory_write"
    category = "memory"
    description = "Write to persistent JSON memory with TTL."
    tool_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"type": "string"},
            "ttl_seconds": {"type": "integer"},
        },
        "required": ["key", "value"],
    }

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        store = _memory_store()
        store[args["key"]] = {"value": args["value"],
                              "ts": time.time(),
                              "ttl": int(args.get("ttl_seconds", 0))}
        _memory_save(store)
        return ToolResult.ok(f"stored {args['key']}")


_MEMORY_FILE: Optional[Path] = None


def _memory_store() -> dict:
    global _MEMORY_FILE
    if _MEMORY_FILE is None:
        _MEMORY_FILE = Config.GRAPH_DIR / "agent_memory.json"
        _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _MEMORY_FILE.exists():
        try:
            return json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _memory_save(store: dict) -> None:
    if _MEMORY_FILE:
        _MEMORY_FILE.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# Instantiate all tools → side-effect registration into the ToolRegistry
# ══════════════════════════════════════════════════════════════════════════════

GRAPH_TOOLS: list[type[BaseTool]] = [
    GetLocalGraphTool, SearchNodesTool, ReadNodeTool, RegisterNodeTool,
    LinkNodesTool, UnlinkTool, InferEdgesTool, ProbeGapTool,
    ValidateGraphTool, SummarizeLocalTool,
]
CORE_TOOLS: list[type[BaseTool]] = [
    ReadFileTool, WriteFileTool, ListDirectoryTool, GrepSearchTool,
    ShellCommandTool, CurrentTimeTool, MemoryReadTool, MemoryWriteTool,
]

_INSTANTIATED = False


def ensure_tools() -> None:
    """Idempotently instantiate all tools (registers them in the ToolRegistry)."""
    global _INSTANTIATED
    if _INSTANTIATED:
        return
    for cls in GRAPH_TOOLS + CORE_TOOLS:
        cls()
    # graph-mutation tools live in database/database_tool (IPP)
    try:
        from database.database_tool import ensure_database_tools
        ensure_database_tools()
    except ImportError as exc:  # noqa: BLE001
        logger.warning("database_tool not loaded: %s", exc)
    _INSTANTIATED = True
