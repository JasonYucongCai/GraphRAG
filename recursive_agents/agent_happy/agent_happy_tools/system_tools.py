"""
agent_a1_tools.system_tools — System info tools (5 tools)

current_time, get_environment, check_python_version,
list_installed_packages, get_system_info
"""
from __future__ import annotations
import json, os, platform, sys, time
from typing import Any
from .tool_base import ReadOnlyTool, ToolContext, ToolResult


class CurrentTimeTool(ReadOnlyTool):
    tool_name = "current_time"
    category = "system"
    description = "Get the current date and time."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        now = time.time()
        return ToolResult.success(
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))} "
            f"(unix: {int(now)})",
            timestamp=now, iso=time.strftime("%Y-%m-%dT%H:%M:%S",
                                            time.localtime(now)))


class GetEnvironmentTool(ReadOnlyTool):
    tool_name = "get_environment"
    category = "system"
    description = "Get environment variables (excluding secrets)."
    tool_schema = {
        "type": "object",
        "properties": {
            "keys": {"type": "array", "items": {"type": "string"},
                    "description": "Specific keys to get (omit for safe defaults)."},
        },
    }
    SAFE_KEYS = ["PATH", "PYTHONPATH", "USERNAME", "USER", "HOME",
                 "HOMEPATH", "COMPUTERNAME", "TEMP", "TMP",
                 "VIRTUAL_ENV", "CONDA_PREFIX", "CUDA_VISIBLE_DEVICES"]

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        keys = args.get("keys", self.SAFE_KEYS)
        env = {k: os.environ.get(k, "(not set)") for k in keys}
        return ToolResult.success(
            json.dumps(env, ensure_ascii=False, indent=2),
            key_count=len(env))


class CheckPythonVersionTool(ReadOnlyTool):
    tool_name = "check_python_version"
    category = "system"
    description = "Check the current Python version and executable."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.success(
            f"Python {sys.version}\nExecutable: {sys.executable}",
            version=sys.version, executable=sys.executable,
            version_info=list(sys.version_info))


class ListInstalledPackagesTool(ReadOnlyTool):
    tool_name = "list_installed_packages"
    category = "system"
    description = "List installed Python packages (top-level only)."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            import pkg_resources
            pkgs = sorted([f"{d.project_name}=={d.version}"
                          for d in pkg_resources.working_set])
            return ToolResult.success(
                "\n".join(pkgs[:100]),
                total_count=len(pkgs), shown=min(len(pkgs), 100))
        except ImportError:
            # Fallback: pip list
            import subprocess
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "list", "--format=columns"],
                    capture_output=True, text=True, timeout=30)
                return ToolResult.success(r.stdout[:4000])
            except Exception as e:
                return ToolResult.fail(str(e))


class GetSystemInfoTool(ReadOnlyTool):
    tool_name = "get_system_info"
    category = "system"
    description = "Get comprehensive system information."
    tool_schema = {"type": "object", "properties": {}}
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        info = {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "cwd": os.getcwd(),
            "workspace_root": ctx.workspace_root,
        }
        return ToolResult.success(
            json.dumps(info, ensure_ascii=False, indent=2),
            **info)


def register_system_tools(toolkit) -> None:
    toolkit.register_many([
        CurrentTimeTool(), GetEnvironmentTool(),
        CheckPythonVersionTool(), ListInstalledPackagesTool(),
        GetSystemInfoTool(),
    ])
