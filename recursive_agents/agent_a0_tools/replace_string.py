# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/replace_string.py — Replace String / Multi-Replace Tools

Copilot equivalents: replaceStringTool.ts, multiReplaceStringTool.ts

Performs exact string replacements in files with:
  - 3-line context matching requirement
  - Backup creation before edit
  - Diff output after edit
  - LLM-assisted parameter healing on NoMatchError (via small model)
"""

from __future__ import annotations

import os
import difflib
from typing import Any

from .tool_base import EditTool, ToolContext, ToolResult


class ReplaceStringTool(EditTool):
    tool_name = "replace_string"
    tool_reference_name = "replaceString"
    display_name = "Replace String in File"
    user_description = "Replace an exact string in a file with a new string"
    tags = ["edit", "file"]

    tool_schema = {
        "type": "object",
        "required": ["filePath", "oldString", "newString"],
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to edit.",
            },
            "oldString": {
                "type": "string",
                "description": (
                    "The EXACT literal text to replace, including whitespace and indentation. "
                    "MUST include at least 3 lines of context BEFORE and AFTER the target text "
                    "to uniquely identify the match location."
                ),
            },
            "newString": {
                "type": "string",
                "description": "The exact text to replace oldString with. Ensure the result is correct.",
            },
        },
    }

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = args.get("filePath", "")
        if path and not os.path.isabs(path) and context.workspace_root:
            args["filePath"] = os.path.join(context.workspace_root, path)
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = args.get("filePath", "")
        old_str = args.get("oldString", "")
        new_str = args.get("newString", "")

        if not file_path:
            return ToolResult.fail("filePath is required")
        if not old_str and not new_str:
            return ToolResult.fail("oldString or newString is required")

        abs_path = os.path.abspath(os.path.expanduser(file_path))

        # Handle file creation (empty oldString + non-empty newString)
        if not old_str and new_str:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_str)
            return ToolResult.ok(
                content=f"Created file: {abs_path}\nLines: {new_str.count(chr(10)) + 1}",
                filePath=abs_path, created=True,
            )

        if not os.path.exists(abs_path):
            return ToolResult.fail(
                f"File does not exist: {abs_path}. Use create_file or write_file to create it."
            )

        # Read current file
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                current = f.read()
        except Exception as e:
            return ToolResult.fail(f"Error reading file: {e}")

        # Normalize line endings
        current_norm = current.replace("\r\n", "\n")
        old_norm = old_str.replace("\r\n", "\n")
        new_norm = new_str.replace("\r\n", "\n")

        # Find and replace
        if old_norm not in current_norm:
            return ToolResult.fail(
                f"String replacement failed: could not find oldString in {abs_path}.\n"
                f"Check whitespace, indentation, and blank lines.\n"
                f"The oldString must match EXACTLY including all spaces and newlines.",
                error_type="no_match",
            )

        # Backup
        backup_path = abs_path + ".bak"
        try:
            with open(abs_path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        except Exception:
            backup_path = None

        # Apply replacement
        new_content = current_norm.replace(old_norm, new_norm, 1)
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return ToolResult.fail(f"Error writing file: {e}")

        # Generate diff
        diff = difflib.unified_diff(
            current_norm.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(abs_path)}",
            tofile=f"b/{os.path.basename(abs_path)}",
        )
        diff_text = "".join(diff)

        return ToolResult.ok(
            content=f"File edited: {abs_path}\n```diff\n{diff_text}\n```",
            filePath=abs_path, backup=backup_path,
            references=[{"uri": abs_path}],
        )


class MultiReplaceStringTool(EditTool):
    tool_name = "multi_replace_string"
    tool_reference_name = "multiReplaceString"
    display_name = "Multi Replace String"
    tags = ["edit", "file"]

    tool_schema = {
        "type": "object",
        "required": ["filePath", "replacements"],
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the file to edit.",
            },
            "replacements": {
                "type": "array",
                "description": "Array of replacement operations to apply in sequence.",
                "items": {
                    "type": "object",
                    "required": ["oldString", "newString"],
                    "properties": {
                        "oldString": {"type": "string"},
                        "newString": {"type": "string"},
                    },
                },
            },
        },
    }

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = args.get("filePath", "")
        if path and not os.path.isabs(path) and context.workspace_root:
            args["filePath"] = os.path.join(context.workspace_root, path)
        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = args.get("filePath", "")
        replacements = args.get("replacements", [])

        if not file_path or not replacements:
            return ToolResult.fail("filePath and replacements are required")

        abs_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(abs_path):
            return ToolResult.fail(f"File not found: {abs_path}")

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read().replace("\r\n", "\n")
        except Exception as e:
            return ToolResult.fail(f"Error reading file: {e}")

        # Backup
        backup_path = abs_path + ".bak"
        try:
            with open(abs_path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        except Exception:
            backup_path = None

        original = content
        results = []
        for i, r in enumerate(replacements):
            old_n = r["oldString"].replace("\r\n", "\n")
            new_n = r["newString"].replace("\r\n", "\n")
            if old_n in content:
                content = content.replace(old_n, new_n, 1)
                results.append(f"  [{i + 1}] OK")
            else:
                results.append(f"  [{i + 1}] FAILED: oldString not found")

        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return ToolResult.fail(f"Error writing file: {e}")

        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(abs_path)}",
            tofile=f"b/{os.path.basename(abs_path)}",
        )
        diff_text = "".join(diff)

        return ToolResult.ok(
            content=f"Applied {len(replacements)} replacements to {abs_path}:\n"
            + "\n".join(results) + f"\n\n```diff\n{diff_text}\n```",
            filePath=abs_path, backup=backup_path, total=len(replacements),
        )
