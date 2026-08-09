"""
agent_a1_tools.file_tools — File I/O tools (6 tools)

read_file, write_file, replace_string, multi_replace_string,
create_directory, list_directory
"""
from __future__ import annotations
import os, difflib, json
from pathlib import Path
from typing import Any
from .tool_base import BaseTool, ReadOnlyTool, EditTool, ToolContext, ToolResult


class ReadFileTool(ReadOnlyTool):
    tool_name = "read_file"
    category = "file"
    description = "Read the contents of a file. Specify a line range, or omit for entire file."
    tool_schema = {
        "type": "object", "required": ["filePath"],
        "properties": {
            "filePath": {"type": "string", "description": "Absolute path to the file."},
            "startLine": {"type": "number", "description": "Line to start reading from (1-based)."},
            "endLine": {"type": "number", "description": "Line to end reading at (inclusive, 1-based)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        if not path or not os.path.isfile(path):
            return ToolResult.fail(f"File not found: {path!r}")
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            start = int(args.get("startLine", 1)) - 1
            end = int(args.get("endLine", len(text.splitlines())))
            lines = text.splitlines()[max(0, start):end]
            return ToolResult.success("\n".join(lines),
                                      filePath=path, total_lines=len(text.splitlines()),
                                      read_lines=len(lines))
        except Exception as e:
            return ToolResult.fail(f"Error reading {path}: {e}")


class WriteFileTool(EditTool):
    tool_name = "write_file"
    category = "file"
    description = "Create or overwrite a file with the given content. Creates parent directories as needed."
    tool_schema = {
        "type": "object", "required": ["filePath", "content"],
        "properties": {
            "filePath": {"type": "string", "description": "Absolute path to write to."},
            "content": {"type": "string", "description": "Content to write."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        content = args.get("content", "")
        if not path:
            return ToolResult.fail("filePath is required")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            existed = p.exists()
            p.write_text(content, encoding="utf-8")
            return ToolResult.success(
                f"{'Updated' if existed else 'Created'}: {path}",
                filePath=path, size=len(content), existed=existed)
        except Exception as e:
            return ToolResult.fail(f"Write failed: {e}")


class ReplaceStringTool(EditTool):
    tool_name = "replace_string"
    category = "file"
    description = "Replace an exact string in a file. oldString must match exactly once."
    tool_schema = {
        "type": "object", "required": ["filePath", "oldString", "newString"],
        "properties": {
            "filePath": {"type": "string", "description": "Absolute path to the file."},
            "oldString": {"type": "string", "description": "Exact text to replace."},
            "newString": {"type": "string", "description": "Replacement text."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        old = args.get("oldString", "")
        new = args.get("newString", "")
        try:
            text = Path(path).read_text(encoding="utf-8")
            count = text.count(old)
            if count == 0:
                return ToolResult.fail("oldString not found in file")
            if count > 1:
                return ToolResult.fail(f"oldString found {count} times — must be unique")
            Path(path).write_text(text.replace(old, new, 1), encoding="utf-8")
            return ToolResult.success(f"Replaced in {path}", filePath=path)
        except Exception as e:
            return ToolResult.fail(f"Replace failed: {e}")


class MultiReplaceStringTool(EditTool):
    tool_name = "multi_replace_string"
    category = "file"
    description = "Apply multiple replace_string operations atomically."
    tool_schema = {
        "type": "object", "required": ["filePath", "replacements"],
        "properties": {
            "filePath": {"type": "string"},
            "replacements": {"type": "array", "items": {"type": "object", "properties": {
                "oldString": {"type": "string"}, "newString": {"type": "string"},
            }}},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        reps = args.get("replacements", [])
        try:
            text = Path(path).read_text(encoding="utf-8")
            for r in reps:
                text = text.replace(r["oldString"], r["newString"], 1)
            Path(path).write_text(text, encoding="utf-8")
            return ToolResult.success(f"Applied {len(reps)} replacements", count=len(reps))
        except Exception as e:
            return ToolResult.fail(str(e))


class CreateDirectoryTool(EditTool):
    tool_name = "create_directory"
    category = "file"
    description = "Create a directory (and all parent directories)."
    tool_schema = {
        "type": "object", "required": ["dirPath"],
        "properties": {
            "dirPath": {"type": "string", "description": "Absolute path to create."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("dirPath", "")
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return ToolResult.success(f"Directory ready: {path}", dirPath=path)
        except Exception as e:
            return ToolResult.fail(str(e))


class ListDirectoryTool(ReadOnlyTool):
    tool_name = "list_directory"
    category = "file"
    description = "List the contents of a directory."
    tool_schema = {
        "type": "object", "required": ["path"],
        "properties": {
            "path": {"type": "string", "description": "Absolute path to list."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("path", "")
        try:
            items = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                items.append(name + ("/" if os.path.isdir(full) else ""))
            return ToolResult.success("\n".join(items), path=path, count=len(items))
        except Exception as e:
            return ToolResult.fail(str(e))


def register_file_tools(toolkit) -> None:
    toolkit.register_many([
        ReadFileTool(), WriteFileTool(), ReplaceStringTool(),
        MultiReplaceStringTool(), CreateDirectoryTool(), ListDirectoryTool(),
    ])
