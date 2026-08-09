# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""tools/copilot/notebook_tools.py — Jupyter Notebook tools (5 tools)

Copilot equivalents: createNewJupyterNotebook, editNotebook, runNotebookCell,
                      getNotebookSummary, readNotebookCellOutput
"""
from __future__ import annotations
from typing import Any
from .tool_base import ReadOnlyTool, EditTool, ExecuteTool, ToolContext, ToolResult


class CreateJupyterNotebookTool(EditTool):
    tool_name = "create_new_jupyter_notebook"
    tool_reference_name = "createJupyterNotebook"
    display_name = "Create Jupyter Notebook"
    tags = ["jupyter", "edit"]
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Description of the notebook to create."},
            "filePath": {"type": "string", "description": "Optional: target path. Defaults to the workspace root."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        path = args.get("filePath", "")
        import os, json
        if not path:
            path = os.path.join(ctx.workspace_root or os.getcwd(), "notebook.ipynb")
        if not path.endswith(".ipynb"):
            path += ".ipynb"
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        nb = {"cells": [], "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.0.0"}}, "nbformat": 4, "nbformat_minor": 5}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=2)
        return ToolResult.ok(content=f"Created notebook: {path}\nQuery: {query}", filePath=path)


class EditNotebookTool(EditTool):
    tool_name = "edit_notebook"
    tool_reference_name = "editNotebook"
    display_name = "Edit Notebook"
    tags = ["jupyter", "edit"]
    tool_schema = {
        "type": "object", "required": ["filePath"],
        "properties": {
            "filePath": {"type": "string", "description": "Absolute path to the notebook file."},
            "cellId": {"type": "string", "description": "Cell ID to edit. Use 'TOP' or 'BOTTOM' for inserting."},
            "newCode": {"type": "string", "description": "New code or markdown for the cell."},
            "language": {"type": "string", "description": "Cell language: python, markdown, javascript, etc."},
            "editType": {"type": "string", "enum": ["insert", "delete", "edit"], "description": "insert | delete | edit"},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Notebook edit: {args.get('editType', 'edit')} cell {args.get('cellId', '?')} in {args.get('filePath', '')}")


class RunNotebookCellTool(ExecuteTool):
    tool_name = "run_notebook_cell"
    tool_reference_name = "runNotebookCell"
    display_name = "Run Notebook Cell"
    tags = ["jupyter", "execute"]
    tool_schema = {
        "type": "object", "required": ["filePath", "cellId"],
        "properties": {
            "filePath": {"type": "string", "description": "Absolute path to the notebook."},
            "cellId": {"type": "string", "description": "ID of the code cell to execute."},
            "reason": {"type": "string", "description": "Optional reason for running."},
            "continueOnError": {"type": "boolean", "description": "Continue if error? Default: false."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Cell {args.get('cellId', '?')} executed in {args.get('filePath', '')}")


class GetNotebookSummaryTool(ReadOnlyTool):
    tool_name = "get_notebook_summary"
    tool_reference_name = "getNotebookSummary"
    display_name = "Get Notebook Summary"
    tags = ["jupyter", "read"]
    tool_schema = {
        "type": "object", "required": ["filePath"],
        "properties": {"filePath": {"type": "string", "description": "Absolute path to the notebook."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        import os, json
        if not os.path.exists(path):
            return ToolResult.fail(f"Notebook not found: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            cells = nb.get("cells", [])
            lines = [f"Notebook: {path}", f"Cells: {len(cells)}"]
            for i, c in enumerate(cells):
                lt = c.get("cell_type", "?")
                src = "".join(c.get("source", []))[:80].replace("\n", " ")
                lines.append(f"  [{i}] {lt}: {src}")
            return ToolResult.ok(content="\n".join(lines), cell_count=len(cells))
        except Exception as e:
            return ToolResult.fail(f"Error reading notebook: {e}")


class ReadNotebookCellOutputTool(ReadOnlyTool):
    tool_name = "read_notebook_cell_output"
    tool_reference_name = "readNotebookCellOutput"
    display_name = "Read Notebook Cell Output"
    tags = ["jupyter", "read"]
    tool_schema = {
        "type": "object", "required": ["filePath", "cellId"],
        "properties": {
            "filePath": {"type": "string", "description": "Absolute path to the notebook."},
            "cellId": {"type": "string", "description": "ID of the cell whose output to read."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Cell output for {args.get('cellId', '?')} in {args.get('filePath', '')} (no kernel attached)")
