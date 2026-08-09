# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/search_tools.py — File Search, Text Search, List Directory, Codebase Search

Copilot equivalents: findFilesTool.ts, findTextInFilesTool.ts, listDirTool.ts, codebaseTool.ts
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
from typing import Any

from .tool_base import ReadOnlyTool, ToolContext, ToolResult


# ── Glob File Search ─────────────────────────────────────────────────

class SearchFilesTool(ReadOnlyTool):
    tool_name = "search_files"
    tool_reference_name = "fileSearch"
    display_name = "Search Files (Glob)"
    user_description = "Search for files by glob pattern"
    tags = ["search"]
    MAX_RESULTS = 100

    tool_schema = {
        "type": "object",
        "required": ["pattern"],
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g., '**/*.py' or 'src/**/*.ts'. Prepend **/ for recursive.",
            },
            "max_results": {
                "type": "number",
                "description": f"Max results. Default 20, max {MAX_RESULTS}.",
            },
        },
    }

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        pattern = args.get("pattern", args.get("query", ""))
        # Normalize: if no **/ prefix and no /, prepend **/
        if pattern and "/" not in pattern and not pattern.startswith("**"):
            args["pattern"] = f"**/{pattern}"
        if pattern.endswith("/"):
            args["pattern"] = pattern + "**"
        args.setdefault("max_results", 20)
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        pattern = args.get("pattern", "")
        max_results = min(int(args.get("max_results", 20)), self.MAX_RESULTS)
        root = context.workspace_root or context.working_directory or "."

        if not pattern:
            return ToolResult.fail("pattern is required")

        matches = []
        start = time.time()
        for dirpath, dirnames, filenames in os.walk(root):
            if context.is_cancelled():
                return ToolResult.fail("Cancelled", error_type="cancelled")
            if time.time() - start > 20:
                break

            # Skip hidden and common ignore dirs
            dirnames[:] = [d for d in dirnames if not d.startswith(".")
                          and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build")]

            rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""

            for fname in filenames:
                if fname.startswith("."):
                    continue
                rel_path = f"{rel_dir}/{fname}" if rel_dir else fname
                rel_path = rel_path.lstrip("/")
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(fname, pattern):
                    abs_path = os.path.join(dirpath, fname)
                    try:
                        stat = os.stat(abs_path)
                        matches.append({
                            "path": rel_path,
                            "abs_path": abs_path,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        })
                    except OSError:
                        matches.append({"path": rel_path, "abs_path": abs_path})

                if len(matches) >= max_results * 2:
                    break
            if len(matches) >= max_results * 2:
                break

        # Sort: newest first
        matches.sort(key=lambda m: m.get("mtime", 0), reverse=True)
        truncated = len(matches) > max_results
        matches = matches[:max_results]

        if not matches:
            return ToolResult.ok(content=f"No files matching {pattern!r}", pattern=pattern, count=0)

        lines = [f"Found {len(matches)} file(s) matching {pattern!r}"]
        if truncated:
            lines.append(f"(showing newest {max_results} of {len(matches) + max_results})")
        lines.append("")
        for m in matches:
            size_str = format_size(m.get("size", 0))
            lines.append(f"  {m['path']} ({size_str})")

        return ToolResult.ok(
            content="\n".join(lines),
            pattern=pattern, count=len(matches), references=[
                {"uri": m["abs_path"]} for m in matches
            ],
        )


# ── Text Search (grep) ───────────────────────────────────────────────

class GrepSearchTool(ReadOnlyTool):
    tool_name = "grep_search"
    tool_reference_name = "textSearch"
    display_name = "Text Search (Grep)"
    user_description = "Search file contents with regex or literal text"
    tags = ["search"]
    MAX_MATCHES = 30

    tool_schema = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "The text or regex pattern to search for.",
            },
            "is_regex": {
                "type": "boolean",
                "description": "Whether query is a regex. Default: false.",
            },
            "include_pattern": {
                "type": "string",
                "description": "Glob pattern to filter files, e.g., 'src/**/*.py'.",
            },
            "max_matches": {
                "type": "number",
                "description": f"Max matches. Default {MAX_MATCHES}.",
            },
            "ignore_case": {
                "type": "boolean",
                "description": "Case-insensitive search. Default: true.",
            },
            "include_ignored": {
                "type": "boolean",
                "description": "Search hidden dirs and .gitignored files. Default: false.",
            },
        },
    }

    BINARY_EXTS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".zip", ".tar", ".gz",
                   ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".ttf", ".eot"}

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        # Fix common LLM errors
        if "pattern" in args and "query" not in args:
            args["query"] = args.pop("pattern")
        if "regex" in args and "is_regex" not in args:
            args["is_regex"] = args.pop("regex")
        args.setdefault("ignore_case", True)
        args.setdefault("max_matches", self.MAX_MATCHES)
        args.setdefault("include_ignored", False)
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        query = args.get("query", "")
        is_regex = args.get("is_regex", False)
        include_pat = args.get("include_pattern", "")
        max_matches = min(int(args.get("max_matches", self.MAX_MATCHES)), 200)
        ignore_case = args.get("ignore_case", True)
        include_ignored = args.get("include_ignored", False)
        root = context.workspace_root or context.working_directory or "."

        if not query:
            return ToolResult.fail("query is required")

        # Compile pattern
        try:
            flags = re.IGNORECASE if ignore_case else 0
            if is_regex:
                pattern = re.compile(query, flags)
            else:
                pattern = re.compile(re.escape(query), flags)
        except re.error as e:
            return ToolResult.fail(f"Invalid regex: {e}. Set is_regex=false for literal search.")

        results: list[dict] = []
        start = time.time()

        for dirpath, dirnames, filenames in os.walk(root):
            if context.is_cancelled():
                return ToolResult.fail("Cancelled", error_type="cancelled")
            if time.time() - start > 20:
                break

            # Filter hidden/ignored
            if not include_ignored:
                dirnames[:] = [d for d in dirnames
                              if not d.startswith(".")
                              and d not in ("node_modules", "__pycache__", ".git", "venv")]
                filenames = [f for f in filenames if not f.startswith(".")]

            # Glob filter
            if include_pat:
                rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
                filenames = [
                    f for f in filenames
                    if fnmatch.fnmatch(f"{rel_dir}/{f}".lstrip("/"), include_pat)
                    or fnmatch.fnmatch(f, include_pat)
                ]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.BINARY_EXTS:
                    continue

                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, root).replace("\\", "/")

                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_no, line in enumerate(f, 1):
                            match = pattern.search(line)
                            if match:
                                results.append({
                                    "file": rel_path,
                                    "line": line_no,
                                    "col": match.start() + 1,
                                    "content": line.rstrip()[:200],
                                })
                                if len(results) >= max_matches * 2:
                                    break
                except Exception:
                    continue

                if len(results) >= max_matches * 2:
                    break

        results.sort(key=lambda r: (r["file"], r["line"]))
        truncated = len(results) > max_matches
        results = results[:max_matches]

        if not results:
            return ToolResult.ok(content=f"No matches for {query!r}", query=query, count=0)

        # Format output
        by_file: dict[str, list] = {}
        for r in results:
            by_file.setdefault(r["file"], []).append(r)

        output = [f"Found {sum(len(v) for v in by_file.values())} match(es) for {query!r}"]
        if truncated:
            output.append(f"(showing first {max_matches})")
        output.append("")
        for fname, matches in by_file.items():
            output.append(f"── {fname} ──")
            for m in matches:
                output.append(f"  {m['line']}:{m['col']}  {m['content']}")

        return ToolResult.ok(
            content="\n".join(output),
            query=query, count=sum(len(v) for v in by_file.values()),
            references=[{"uri": os.path.join(root, r["file"])} for r in results[:5]],
        )


# ── List Directory ───────────────────────────────────────────────────

class ListDirectoryTool(ReadOnlyTool):
    tool_name = "list_directory"
    tool_reference_name = "listDir"
    display_name = "List Directory"
    tags = ["read"]
    MAX_ENTRIES = 200

    tool_schema = {
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {
                "type": "string",
                "description": "The absolute path of the directory to list.",
            },
            "show_hidden": {
                "type": "boolean",
                "description": "Show hidden files (starting with .). Default: false.",
            },
        },
    }

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = args.get("path", "")
        if path and not os.path.isabs(path) and context.workspace_root:
            args["path"] = os.path.join(context.workspace_root, path)
        if not path:
            args["path"] = context.workspace_root or "."
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        path = args.get("path", ".")
        show_hidden = args.get("show_hidden", False)
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not os.path.exists(abs_path):
            return ToolResult.fail(f"Directory not found: {abs_path}")
        if not os.path.isdir(abs_path):
            return ToolResult.fail(f"Not a directory: {abs_path}. Use read_file to read files.")

        try:
            entries = os.listdir(abs_path)
        except PermissionError:
            return ToolResult.fail(f"Permission denied: {abs_path}")

        dirs, files = [], []
        for name in entries:
            if not show_hidden and name.startswith("."):
                continue
            full = os.path.join(abs_path, name)
            try:
                stat = os.stat(full)
                if os.path.isdir(full):
                    dirs.append((name, stat))
                else:
                    files.append((name, stat))
            except OSError:
                pass

        if not dirs and not files:
            return ToolResult.ok(content=f"Directory is empty: {abs_path}")

        dirs.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())

        lines = [f"Contents of: {abs_path}", ""]
        for name, stat in dirs:
            lines.append(f"  📁 {name}/")
        for name, stat in files:
            lines.append(f"  📄 {name} ({format_size(stat.st_size)})")

        if len(lines) > self.MAX_ENTRIES:
            lines = lines[:self.MAX_ENTRIES] + [f"... ({len(lines) - self.MAX_ENTRIES} more entries)"]

        return ToolResult.ok(
            content="\n".join(lines),
            path=abs_path, dirs=len(dirs), files=len(files),
        )


# ── Helpers ──────────────────────────────────────────────────────────

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
