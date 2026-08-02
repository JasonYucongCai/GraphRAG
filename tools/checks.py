"""
tools.checks — review & audit tools for the agentic chat (IPP, read-only).

  • review_top_threats — scan the project for the top security/threat issues
  • standard_check     — standard quality/compliance checks (structure, syntax)
  • advanced_check     — deeper audit (secrets, stale artifacts, sizes)

All three are READ-ONLY: they only grep/read files and the graph; they never
write. They are IPP BaseTools registered in the shared ToolRegistry.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from tools.config import Config
from tools.ipp import BaseTool, ToolContext, ToolResult

SKIP_DIRS = {"__pycache__", ".git", ".vscode", "node_modules", "graph_data", "assets"}

# patterns that suggest risk / threat
THREAT_PATTERNS = [
    (r"(?i)sk-[a-zA-Z0-9]{20,}", "exposed API key (sk-…)"),
    (r"(?i)api[_-]?key\s*[=:]\s*['\"][^'\"]{8,}", "api key literal"),
    (r"(?i)password\s*[=:]\s*['\"][^'\"]{6,}", "password literal"),
    (r"(?i)secret\s*[=:]\s*['\"][^'\"]{8,}", "secret literal"),
    (r"(?i)token\s*[=:]\s*['\"][^'\"]{12,}", "token literal"),
    (r"(?i)\brm\s+-rf\s+/", "destructive rm"),
    (r"(?i)\beval\s*\(", "eval()"),
    (r"(?i)\bexec\s*\(", "exec()"),
    (r"(?i)subprocess\.(run|Popen|call)", "subprocess usage"),
    (r"(?i)pickle\.loads?", "unsafe pickle"),
    (r"(?i)sql\s*\+", "string-concatenated SQL"),
]


def _iter_files(root: Path, exts=(".py", ".js", ".ts", ".md", ".txt", ".json", ".html", ".env", ".cfg")):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(exts) or fn in (".env",):
                yield Path(dp) / fn


class ReviewTopThreatsTool(BaseTool):
    tool_name = "review_top_threats"
    category = "audit"
    description = ("Scan the project for the top security threats / risks "
                   "(exposed keys, secrets, dangerous patterns). READ-ONLY.")
    tool_schema = {"type": "object", "properties": {}, "required": []}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace_root or Config.WORKSPACE_ROOT)
        found: list[dict] = []
        for path in _iter_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat, label in THREAT_PATTERNS:
                for m in re.finditer(pat, text):
                    found.append({
                        "file": str(path.relative_to(root)),
                        "line": text[: m.start()].count("\n") + 1,
                        "threat": label,
                        "snippet": m.group(0)[:60],
                    })
                    break  # one per pattern per file
        found.sort(key=lambda x: (x["threat"], x["file"]))
        top = found[:15]
        lines = [f"top threats: {len(found)} candidate(s) found", ""]
        for t in top:
            lines.append(f"  ⚠ {t['threat']} — {t['file']}:{t['line']}  {t['snippet']!r}")
        if not top:
            lines.append("  (none detected)")
        return ToolResult.ok("\n".join(lines), count=len(found))


class StandardCheckTool(BaseTool):
    tool_name = "standard_check"
    category = "audit"
    description = ("Standard project check: structure, required files, Python "
                   "syntax, graph consistency. READ-ONLY.")
    tool_schema = {"type": "object", "properties": {}, "required": []}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace_root or Config.WORKSPACE_ROOT)
        checks: list[str] = []
        problems: list[str] = []

        # required files
        for req in ("README.md", "requirements.txt", "LICENSE"):
            if (root / req).exists():
                checks.append(f"✓ {req} present")
            else:
                problems.append(f"✗ missing {req}")

        # python syntax (compile)
        syn_errs = 0
        for path in _iter_files(root, exts=(".py",)):
            try:
                compile(path.read_text(encoding="utf-8", errors="ignore"), str(path), "exec")
            except (SyntaxError, OSError):
                syn_errs += 1
                problems.append(f"✗ syntax error in {path.relative_to(root)}")
        checks.append(f"✓ python files compiled ({syn_errs} syntax errors)")

        # graph consistency
        graph = ctx.extra.get("graph") or (getattr(ctx.agent, "graph", None) if ctx.agent else None)
        if graph is not None:
            viol = len(graph.validate_consistency())
            checks.append(f"✓ graph: {len(graph._nodes)} nodes, {len(graph._edges)} edges, {viol} violations")
            if viol:
                problems.append(f"✗ {viol} graph consistency violations")
        else:
            checks.append("· graph not bound — skipping consistency")

        return ToolResult.ok("\n".join(checks + (["", "PROBLEMS:"] + problems if problems else ["", "all standard checks passed"])))


class AdvancedCheckTool(BaseTool):
    tool_name = "advanced_check"
    category = "audit"
    description = ("Advanced audit: large files, stale artifacts, .env exposure, "
                   "dependency pins, TODOs/FIXMEs. READ-ONLY.")
    tool_schema = {"type": "object", "properties": {}, "required": []}

    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        root = Path(ctx.workspace_root or Config.WORKSPACE_ROOT)
        lines: list[str] = ["advanced audit"]

        # large files
        big = []
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                p = Path(dp) / fn
                try:
                    if p.stat().st_size > 2_000_000:
                        big.append(f"{p.relative_to(root)} ({p.stat().st_size/1e6:.1f} MB)")
                except OSError:
                    pass
        lines.append(f"large files (>2MB): {len(big)}" + (":\n  " + "\n  ".join(big[:8]) if big else ""))

        # .env exposure
        envs = list(root.rglob(".env"))
        lines.append(f".env files: {len(envs)}")
        for e in envs[:4]:
            rel = e.relative_to(root)
            lines.append(f"  · {rel} {'⚠ in repo' if '.git' not in str(e) else ''}")

        # TODO / FIXME count
        todo = 0
        for p in _iter_files(root, exts=(".py", ".js", ".md")):
            try:
                todo += len(re.findall(r"(?i)\b(TODO|FIXME|HACK)\b", p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
        lines.append(f"TODO/FIXME markers: {todo}")

        # dependency pins
        req = root / "requirements.txt"
        if req.exists():
            unpinned = [ln.strip().split("#")[0].strip() for ln in req.read_text(encoding="utf-8").splitlines()
                        if ln.strip() and not ln.strip().startswith("#") and ">=" not in ln and "==" not in ln]
            lines.append(f"requirements: {len(unpinned)} unpinned entries")

        return ToolResult.ok("\n".join(lines))


CHECK_TOOLS = [ReviewTopThreatsTool, StandardCheckTool, AdvancedCheckTool]

_INSTANTIATED = False


def ensure_check_tools() -> None:
    global _INSTANTIATED
    if _INSTANTIATED:
        return
    for cls in CHECK_TOOLS:
        cls()
    _INSTANTIATED = True
