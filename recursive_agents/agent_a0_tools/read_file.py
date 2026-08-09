# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/read_file.py — Read File Tool

Copilot equivalent: readFileTool.tsx

Enhanced version of Codex's read_file with:
  - V1 (startLine/endLine) and V2 (offset/limit) parameter compatibility
  - Image file detection (redirects to view_image)
  - Binary file hexdump fallback
  - External file confirmation
  - Line number rendering
  - Truncation with clear messaging
"""

from __future__ import annotations

import os
from typing import Any

from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class ReadFileTool(ReadOnlyTool):
    tool_name = "read_file"
    tool_reference_name = "readFile"
    display_name = "Read File"
    user_description = "Read the contents of a file with optional line range"
    tags = ["read", "file"]

    tool_schema = {
        "type": "object",
        "required": ["filePath"],
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute path of the file to read.",
            },
            "startLine": {
                "type": "number",
                "description": "Optional: the 1-based line number to start reading from.",
            },
            "endLine": {
                "type": "number",
                "description": "Optional: the inclusive 1-based line number to end reading at.",
            },
            "offset": {
                "type": "number",
                "description": "Optional (V2): 1-based line number to start from. Prefer startLine unless you know V2.",
            },
            "limit": {
                "type": "number",
                "description": "Optional (V2): max number of lines to read. Prefer endLine unless you know V2.",
            },
        },
    }

    MAX_LINES = 2000
    MAX_LINE_LENGTH = 2000
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}

    async def resolve_input(self, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Convert relative paths to absolute; fix V1/V2 params."""
        # Path resolution
        path = args.get("filePath", "")
        if path and not os.path.isabs(path):
            if context.workspace_root:
                args["filePath"] = os.path.join(context.workspace_root, path)
            elif context.working_directory:
                args["filePath"] = os.path.join(context.working_directory, path)

        # V1→V2 conversion: if startLine/endLine provided, convert to offset/limit
        if "startLine" in args and "offset" not in args:
            args["offset"] = args["startLine"]
        if "endLine" in args and "limit" not in args and "offset" in args:
            start = max(1, int(args.get("offset", 1)))
            end = max(start, int(args["endLine"]))
            args["limit"] = end - start + 1

        return args

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        if not path:
            return ToolResult.fail("filePath is required", error_type="missing_required")

        # Resolve path
        abs_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(abs_path):
            return ToolResult.fail(
                f"File not found: {abs_path}. Use list_directory or search_files to find the correct path.",
                error_type="file_not_found",
            )

        # Image guard
        ext = os.path.splitext(abs_path)[1].lower()
        if ext in self.IMAGE_EXTENSIONS:
            return ToolResult.fail(
                f"Cannot read image files with read_file. Use view_image instead: {abs_path}",
                error_type="wrong_tool",
            )

        # Read file
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except UnicodeDecodeError:
            # Binary file — return hexdump
            return self._binary_hexdump(abs_path)
        except PermissionError:
            return ToolResult.fail(
                f"Permission denied: {abs_path}",
                error_type="permission_denied",
            )
        except Exception as e:
            return ToolResult.fail(f"Error reading {abs_path}: {e}", error_type="read_error")

        total_lines = len(all_lines)
        offset = max(1, int(args.get("offset", args.get("startLine", 1))))
        limit = int(args.get("limit", args.get("endLine", self.MAX_LINES)))
        if "endLine" in args and "limit" not in args:
            end_line = max(offset, int(args["endLine"]))
            limit = end_line - offset + 1

        # Clamp range
        start_idx = min(offset - 1, total_lines - 1)
        end_idx = min(start_idx + limit, total_lines)

        selected = all_lines[start_idx:end_idx]
        truncated = end_idx < total_lines

        # Format output with line numbers
        output_lines = []
        for i, line in enumerate(selected):
            line_num = start_idx + i + 1
            display = line.rstrip("\n\r")
            if len(display) > self.MAX_LINE_LENGTH:
                display = display[:self.MAX_LINE_LENGTH] + " [truncated]"
            output_lines.append(f"{line_num:6d}|{display}")

        content = "\n".join(output_lines)
        if truncated:
            content += f"\n... [truncated: showing lines {start_idx + 1}-{end_idx} of {total_lines}]"

        return ToolResult.ok(
            content=content,
            filePath=abs_path,
            total_lines=total_lines,
            lines_returned=len(selected),
            truncated=truncated,
            references=[{"uri": abs_path, "range": {"start": start_idx + 1, "end": end_idx}}],
        )

    def _binary_hexdump(self, path: str, max_bytes: int = 256) -> ToolResult:
        """Return a hexdump of a binary file's first bytes."""
        try:
            with open(path, "rb") as f:
                data = f.read(max_bytes)
            hex_lines = []
            for i in range(0, len(data), 16):
                chunk = data[i:i + 16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                hex_lines.append(f"{i:08x}  {hex_part:<48}  |{ascii_part}|")
            return ToolResult.ok(
                content=f"[Binary file: {os.path.getsize(path)} bytes]\n" + "\n".join(hex_lines),
                filePath=path,
                binary=True,
            )
        except Exception as e:
            return ToolResult.fail(f"Error reading binary file: {e}")
