"""
agent_a1_tools.code_tools — Code generation & validation (4 tools)

validate_code, compile_check, run_code_snippet, generate_python_file
"""
from __future__ import annotations
import ast, json, os, py_compile, subprocess, sys, tempfile
from pathlib import Path
from typing import Any
from .tool_base import BaseTool, ReadOnlyTool, ExecuteTool, EditTool, ToolContext, ToolResult


class ValidateCodeTool(ReadOnlyTool):
    tool_name = "validate_code"
    category = "code"
    description = "Validate Python code syntax without executing it."
    tool_schema = {
        "type": "object", "required": ["code"],
        "properties": {
            "code": {"type": "string", "description": "Python code to validate."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        code = args.get("code", "")
        if not code:
            return ToolResult.fail("code is required")
        try:
            ast.parse(code)
            return ToolResult.success("Syntax OK", valid=True)
        except SyntaxError as e:
            return ToolResult.success(
                f"Syntax error: {e.msg} (line {e.lineno}, col {e.offset})",
                valid=False, error=str(e), line=e.lineno, col=e.offset)


class CompileCheckTool(ReadOnlyTool):
    tool_name = "compile_check"
    category = "code"
    description = "Check if a Python file compiles without errors."
    tool_schema = {
        "type": "object", "required": ["filePath"],
        "properties": {
            "filePath": {"type": "string", "description": "Path to .py file."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        if not path or not os.path.isfile(path):
            return ToolResult.fail(f"File not found: {path!r}")
        try:
            py_compile.compile(path, doraise=True)
            return ToolResult.success(f"Compiles OK: {path}", filePath=path)
        except py_compile.PyCompileError as e:
            return ToolResult.success(
                f"Compile error: {e}",
                filePath=path, valid=False, error=str(e))


class RunCodeSnippetTool(ExecuteTool):
    tool_name = "run_code_snippet"
    category = "code"
    description = "Run a Python code snippet and return the output."
    tool_schema = {
        "type": "object", "required": ["code"],
        "properties": {
            "code": {"type": "string", "description": "Python code to run."},
            "timeout": {"type": "number", "description": "Timeout in seconds (default: 30)."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        code = args.get("code", "")
        timeout = int(args.get("timeout", 30))
        if not code:
            return ToolResult.fail("code is required")
        try:
            r = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True,
                timeout=min(timeout, 60),
                cwd=ctx.workspace_root or os.getcwd())
            out = r.stdout[:4000]
            err = r.stderr[:1000]
            return ToolResult.success(
                out + (f"\n[stderr]\n{err}" if err else ""),
                exit_code=r.returncode)
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"Timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(str(e))


class GeneratePythonFileTool(EditTool):
    tool_name = "generate_python_file"
    category = "code"
    description = "Generate a Python file with the given content."
    tool_schema = {
        "type": "object", "required": ["filePath", "content"],
        "properties": {
            "filePath": {"type": "string", "description": "Path for the new .py file."},
            "content": {"type": "string", "description": "Python source code."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        content = args.get("content", "")
        if not path or not content:
            return ToolResult.fail("filePath and content are required")
        try:
            # Validate syntax before writing
            ast.parse(content)
        except SyntaxError as e:
            return ToolResult.fail(f"Syntax error in generated code: {e}")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult.success(
                f"Generated: {path} ({len(content)} chars)",
                filePath=path, size=len(content))
        except Exception as e:
            return ToolResult.fail(str(e))


def register_code_tools(toolkit) -> None:
    toolkit.register_many([
        ValidateCodeTool(), CompileCheckTool(),
        RunCodeSnippetTool(), GeneratePythonFileTool(),
    ])
