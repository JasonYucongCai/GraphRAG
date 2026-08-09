# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/write_file.py — Write File / Create File Tool

Copilot equivalent: createFileTool.ts
"""

import os
import difflib
from typing import Any

from .tool_base import EditTool, ToolContext, ToolResult


class WriteFileTool(EditTool):
    tool_name = "write_file"
    tool_reference_name = "createFile"
    display_name = "Write File"
    tags = ["edit", "file"]

    tool_schema = {
        "type": "object",
        "required": ["filePath", "content"],
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to create or overwrite.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
    }

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = args.get("filePath", "")
        if path and not os.path.isabs(path) and context.workspace_root:
            args["filePath"] = os.path.join(context.workspace_root, path)
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        content = args.get("content", "")

        if not path:
            return ToolResult.fail("filePath is required", error_type="missing_required")

        abs_path = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        existed = os.path.exists(abs_path)
        backup_path = None
        old_content = ""

        if existed:
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    old_content = f.read()
            except Exception:
                old_content = "[binary or unreadable]"

            backup_path = abs_path + ".bak"
            try:
                with open(abs_path, "rb") as src:
                    with open(backup_path, "wb") as dst:
                        dst.write(src.read())
            except Exception:
                backup_path = None

        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return ToolResult.fail(f"Error writing file: {e}", error_type="write_error")

        # Generate diff
        diff_text = ""
        if existed and old_content and old_content != "[binary or unreadable]":
            diff = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(abs_path)}",
                tofile=f"b/{os.path.basename(abs_path)}",
            )
            diff_text = "".join(diff)
            if not diff_text:
                diff_text = "(no changes detected)"

        return ToolResult.ok(
            content=f"{'Updated' if existed else 'Created'} file: {abs_path}\n"
            f"Lines: {content.count(chr(10)) + 1}\n"
            + (f"\n```diff\n{diff_text}\n```" if diff_text else ""),
            filePath=abs_path,
            created=not existed,
            backup=backup_path,
            references=[{"uri": abs_path}],
        )


class CreateDirectoryTool(EditTool):
    tool_name = "create_directory"
    tool_reference_name = "createDirectory"
    display_name = "Create Directory"
    tags = ["edit", "file"]

    tool_schema = {
        "type": "object",
        "required": ["dirPath"],
        "properties": {
            "dirPath": {
                "type": "string",
                "description": "The absolute path to the directory to create.",
            },
        },
    }

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = args.get("dirPath", args.get("path", ""))
        if path and not os.path.isabs(path) and context.workspace_root:
            args["dirPath"] = os.path.join(context.workspace_root, path)
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        path = args.get("dirPath", "")
        if not path:
            return ToolResult.fail("dirPath is required", error_type="missing_required")

        abs_path = os.path.abspath(os.path.expanduser(path))
        if os.path.exists(abs_path):
            return ToolResult.ok(content=f"Directory already exists: {abs_path}")

        try:
            os.makedirs(abs_path, exist_ok=True)
            return ToolResult.ok(content=f"Created directory: {abs_path}", dirPath=abs_path)
        except Exception as e:
            return ToolResult.fail(f"Error creating directory: {e}", error_type="create_error")
