# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""tools/copilot/vscode_tools.py — VS Code interaction tools (10 tools)

Copilot equivalents: get_vscode_api, install_extension, run_vscode_command,
    create_new_workspace, resolve_memory_file_uri, session_store_sql,
    search_workspace_symbols, find_test_files, switch_agent, memory (3 scopes)
"""
from __future__ import annotations
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class GetVSCodeAPITool(ReadOnlyTool):
    tool_name = "get_vscode_api"
    tool_reference_name = "vscodeAPI"
    display_name = "Get VS Code API Documentation"
    deferred = True
    tags = ["vscode"]
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {"query": {"type": "string", "description": "VS Code API concept, interface, or feature to look up."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"VS Code API docs for: {args.get('query', '')}\n(API reference: https://code.visualstudio.com/api)")


class InstallExtensionTool(ReadOnlyTool):
    tool_name = "install_extension"
    tool_reference_name = "installExtension"
    display_name = "Install VS Code Extension"
    deferred = True
    tags = ["vscode"]
    tool_schema = {
        "type": "object", "required": ["id"],
        "properties": {
            "id": {"type": "string", "description": "Extension ID: publisher.extension"},
            "name": {"type": "string", "description": "Extension name for display."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        ext_id = args.get("id", "")
        return ToolResult.ok(content=f"Extension {ext_id} — Run: code --install-extension {ext_id}")


class RunVSCodeCommandTool(ReadOnlyTool):
    tool_name = "run_vscode_command"
    tool_reference_name = "runCommand"
    display_name = "Run VS Code Command"
    deferred = True
    tags = ["vscode"]
    tool_schema = {
        "type": "object", "required": ["commandId", "name"],
        "properties": {
            "commandId": {"type": "string", "description": "The command ID."},
            "name": {"type": "string", "description": "Human-readable name."},
            "args": {"type": "array", "items": {"type": "string"}},
            "skipCheck": {"type": "boolean"},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"VS Code command: {args.get('commandId', '')} ({args.get('name', '')})")


class CreateNewWorkspaceTool(ReadOnlyTool):
    tool_name = "create_new_workspace"
    tool_reference_name = "newWorkspace"
    display_name = "Create New Workspace"
    deferred = True
    tags = ["vscode"]
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {"query": {"type": "string", "description": "Description of the project to scaffold."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Workspace scaffolding: {args.get('query', '')}\n(creates project structure with config files, package.json, etc.)")


class ResolveMemoryFileUriTool(ReadOnlyTool):
    tool_name = "resolve_memory_file_uri"
    tool_reference_name = "resolveMemoryFileUri"
    display_name = "Resolve Memory File URI"
    deferred = True
    tags = ["memory"]
    tool_schema = {
        "type": "object", "required": ["path"],
        "properties": {"path": {"type": "string", "description": "Memory path: /memories/notes.md"}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("path", "")
        import os
        full = os.path.join(ctx.workspace_root or ".", path.lstrip("/"))
        return ToolResult.ok(content=f"Memory file: {full}")


class SessionStoreSqlTool(ReadOnlyTool):
    tool_name = "session_store_sql"
    tool_reference_name = "sessionStoreSql"
    display_name = "Session Store SQL"
    deferred = True
    tags = ["vscode"]
    tool_schema = {
        "type": "object", "required": ["description"],
        "properties": {
            "action": {"type": "string", "enum": ["query", "reindex"], "description": "query or reindex."},
            "query": {"type": "string", "description": "SQLite query (SELECT only)."},
            "description": {"type": "string", "description": "What this query does."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Session SQL: {args.get('description', '')}\n(no session store available in codex-local)")


class SearchWorkspaceSymbolsTool(ReadOnlyTool):
    tool_name = "search_workspace_symbols"
    tool_reference_name = "symbols"
    display_name = "Search Workspace Symbols"
    tags = ["search"]
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {"query": {"type": "string", "description": "Symbol name to search for (function, class, variable)."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        import os, re
        root = ctx.workspace_root or "."
        matches = []
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames[:50]:
                if fn.endswith((".py", ".ts", ".js", ".java", ".go", ".rs")):
                    fp = os.path.join(dirpath, fn)
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            for lineno, line in enumerate(f, 1):
                                if query in line:
                                    matches.append(f"{os.path.relpath(fp, root)}:{lineno}: {line.strip()[:120]}")
                    except Exception:
                        pass
                    if len(matches) > 30: break
            if len(matches) > 30: break
        return ToolResult.ok(content="\n".join(matches[:30]) or f"No symbols matching {query!r}")


class FindTestFilesTool(ReadOnlyTool):
    tool_name = "find_test_files"
    tool_reference_name = "findTestFiles"
    display_name = "Find Test Files"
    tags = ["search"]
    tool_schema = {
        "type": "object", "properties": {
            "filePath": {"type": "string", "description": "Source file to find tests for."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        import os
        base = os.path.splitext(os.path.basename(path))[0] if path else ""
        patterns = [f"test_{base}*", f"{base}_test*", f"*test*{base}*"]
        return ToolResult.ok(content=f"Looking for tests matching {base}...\nPatterns: {', '.join(patterns)}")


class SwitchAgentTool(ReadOnlyTool):
    tool_name = "switch_agent"
    tool_reference_name = "switchAgent"
    display_name = "Switch Agent"
    deferred = True
    tags = ["vscode"]
    tool_schema = {
        "type": "object", "required": ["agentId"],
        "properties": {"agentId": {"type": "string", "description": "Agent ID to switch to."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Switching to agent: {args.get('agentId', '')}")
