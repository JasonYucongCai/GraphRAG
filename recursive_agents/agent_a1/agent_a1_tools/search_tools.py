"""
agent_a1_tools.search_tools — Search & Discovery tools (4 tools)

grep_search, file_search, search_nodes, find_references
"""
from __future__ import annotations
import os, re, fnmatch, time
from pathlib import Path
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class GrepSearchTool(ReadOnlyTool):
    tool_name = "grep_search"
    category = "search"
    description = "Fast text search in workspace files. Supports regex."
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Pattern to search for (regex supported)."},
            "isRegexp": {"type": "boolean", "description": "Whether query is a regex."},
            "includePattern": {"type": "string", "description": "Glob to filter files (e.g., '**/*.py')."},
            "maxResults": {"type": "number", "description": "Max results (default 50)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        max_results = int(args.get("maxResults", 50))
        include = args.get("includePattern", "**/*")
        is_regex = args.get("isRegexp", False)
        root = ctx.workspace_root or os.getcwd()

        try:
            pat = re.compile(query, re.IGNORECASE) if is_regex else None
        except Exception:
            pat = None

        results = []
        start = time.time()
        for dirpath, dirnames, filenames in os.walk(root):
            if time.time() - start > 15:
                break
            dirnames[:] = [d for d in dirnames
                          if not d.startswith(".") and d not in
                          ("node_modules", "__pycache__", ".git", "venv", ".venv")]
            for fn in filenames:
                if not fnmatch.fnmatch(fn, include.split("/")[-1] if "/" in include else include):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    text = Path(fp).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if (pat and pat.search(line)) or (not pat and query.lower() in line.lower()):
                        rel = os.path.relpath(fp, root)
                        results.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break
        return ToolResult.success(
            "\n".join(results) if results else f"No matches for: {query[:100]}",
            query=query, match_count=len(results))


class FileSearchTool(ReadOnlyTool):
    tool_name = "file_search"
    category = "search"
    description = "Search for files by glob pattern."
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')."},
            "maxResults": {"type": "number", "description": "Max results."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        pattern = args.get("query", "**/*")
        max_r = int(args.get("maxResults", 50))
        root = ctx.workspace_root or os.getcwd()
        matches = []
        start = time.time()
        for dirpath, dirnames, filenames in os.walk(root):
            if time.time() - start > 10:
                break
            dirnames[:] = [d for d in dirnames
                          if not d.startswith(".") and d not in
                          ("node_modules", "__pycache__", ".git")]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, root).replace("\\", "/")
                if fnmatch.fnmatch(rel, pattern):
                    matches.append(rel)
                    if len(matches) >= max_r:
                        break
            if len(matches) >= max_r:
                break
        return ToolResult.success("\n".join(matches) if matches else f"No files matching {pattern}",
                                  pattern=pattern, count=len(matches))


class SearchNodesTool(ReadOnlyTool):
    tool_name = "search_nodes"
    category = "search"
    description = "Search knowledge graph nodes by name or content."
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Search term."},
            "limit": {"type": "number", "description": "Max results."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        limit = int(args.get("limit", 20))
        tk = ctx.agent
        if tk and tk.graph:
            try:
                nodes = tk.graph.search(query, limit=limit)
                lines = [f"{n.entryname} ({n.node_id})" for n in nodes]
                return ToolResult.success("\n".join(lines) if lines else "No nodes found",
                                          query=query, count=len(lines))
            except Exception as e:
                return ToolResult.fail(str(e))
        return ToolResult.success("(graph not available — offline mode)", query=query)


class FindReferencesTool(ReadOnlyTool):
    tool_name = "find_references"
    category = "search"
    description = "Find all references to a symbol across the workspace."
    tool_schema = {
        "type": "object", "required": ["symbol"],
        "properties": {
            "symbol": {"type": "string", "description": "Symbol name to find."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        symbol = args.get("symbol", "")
        root = ctx.workspace_root or os.getcwd()
        results = []
        start = time.time()
        for dirpath, dirnames, filenames in os.walk(root):
            if time.time() - start > 10:
                break
            dirnames[:] = [d for d in dirnames
                          if not d.startswith(".") and d not in
                          ("node_modules", "__pycache__", ".git")]
            for fn in filenames:
                if not fn.endswith((".py", ".md", ".json", ".txt")):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    for i, line in enumerate(Path(fp).read_text(
                            encoding="utf-8", errors="replace").splitlines(), 1):
                        if symbol in line:
                            rel = os.path.relpath(fp, root)
                            results.append(f"{rel}:{i}: {line.strip()[:150]}")
                except Exception:
                    continue
        return ToolResult.success("\n".join(results[:50]) if results else f"No references to {symbol!r}",
                                  symbol=symbol, count=len(results))


def register_search_tools(toolkit) -> None:
    toolkit.register_many([
        GrepSearchTool(), FileSearchTool(),
        SearchNodesTool(), FindReferencesTool(),
    ])
